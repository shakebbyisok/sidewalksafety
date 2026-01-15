"""
VLM (Vision Language Model) Analysis Service

Analyzes property satellite imagery using Vision Language Models via OpenRouter
to score leads based on user-defined criteria.

OpenRouter allows access to multiple providers (OpenAI, Anthropic, etc.) 
through a single API with the same OpenAI SDK interface.
"""

import logging
import json
import base64
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from openai import AsyncOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)


# Default scoring prompt if user doesn't provide one
DEFAULT_SCORING_PROMPT = """Score this property as a lead for pavement maintenance services:

HIGH SCORE (80-100): Large paved areas (parking lots, driveways) with visible signs of wear, damage, cracks, potholes, or faded line markings. Commercial properties with aging asphalt are ideal leads.

MEDIUM SCORE (40-79): Moderate paved areas with some wear visible, or properties that may need maintenance within 1-2 years. Fair condition but showing age.

LOW SCORE (0-39): Small paved areas, newly paved/well-maintained surfaces, or properties that are mostly buildings and landscaping with minimal pavement."""


@dataclass
class VLMObservations:
    """Structured observations from VLM analysis."""
    paved_area_pct: int  # 0-100
    building_pct: int  # 0-100
    landscaping_pct: int  # 0-100
    condition: str  # excellent, good, fair, poor, critical
    visible_issues: List[str]


@dataclass
class VLMUsageInfo:
    """Usage info from OpenRouter API response."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0  # Actual cost in USD from OpenRouter


@dataclass
class VLMAnalysisResult:
    """Result from VLM property analysis."""
    success: bool
    lead_score: int  # 0-100
    confidence: int  # 0-100
    reasoning: str
    observations: Optional[VLMObservations]
    raw_response: Optional[Dict[str, Any]]
    usage: Optional[VLMUsageInfo] = None  # Actual usage/cost from OpenRouter
    error_message: Optional[str] = None
    
    @classmethod
    def from_error(cls, error: str) -> 'VLMAnalysisResult':
        return cls(
            success=False,
            lead_score=0,
            confidence=0,
            reasoning="",
            observations=None,
            raw_response=None,
            usage=None,
            error_message=error
        )


class VLMAnalysisService:
    """Analyze property images using Vision Language Models via OpenRouter."""
    
    # OpenRouter model names (format: provider/model-name)
    # See available models: https://openrouter.ai/models
    DEFAULT_MODEL = "openai/gpt-4o"  # GPT-4o via OpenRouter
    OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
    
    def __init__(self):
        self.default_client: Optional[AsyncOpenAI] = None
        if settings.OPENROUTER_API_KEY:
            # OpenRouter uses the same OpenAI SDK interface with different base_url
            self.default_client = AsyncOpenAI(
                base_url=self.OPENROUTER_BASE_URL,
                api_key=settings.OPENROUTER_API_KEY,
            )
            logger.info("VLM Analysis Service initialized with OpenRouter (system key)")
        else:
            logger.warning("OPENROUTER_API_KEY not set - VLM analysis requires user's own key")
    
    def _get_client(self, user_api_key: Optional[str] = None) -> Optional[AsyncOpenAI]:
        """Get OpenAI client - uses user's key if provided, otherwise system key."""
        if user_api_key:
            logger.info("  [VLM] Using user's own OpenRouter API key")
            return AsyncOpenAI(
                base_url=self.OPENROUTER_BASE_URL,
                api_key=user_api_key,
            )
        return self.default_client
    
    async def analyze_property(
        self,
        image_base64: str,
        scoring_prompt: Optional[str] = None,
        property_context: Optional[Dict[str, Any]] = None,
        user_api_key: Optional[str] = None,  # User's own OpenRouter key
    ) -> VLMAnalysisResult:
        """
        Analyze a property satellite image and score it as a lead.
        
        Args:
            image_base64: Base64-encoded JPEG image of the property
            scoring_prompt: User's criteria for scoring (uses default if None)
            property_context: Optional dict with Regrid data (address, owner, etc.)
            user_api_key: User's own OpenRouter API key (optional, uses system key if not provided)
            
        Returns:
            VLMAnalysisResult with score, reasoning, and observations
        """
        client = self._get_client(user_api_key)
        if not client:
            return VLMAnalysisResult.from_error("No OpenRouter API key available (set your own in Settings)")
        
        # Use default prompt if not provided
        effective_prompt = scoring_prompt or DEFAULT_SCORING_PROMPT
        
        # Build context string
        context_str = "Not available"
        if property_context:
            context_parts = []
            if property_context.get("address"):
                context_parts.append(f"Address: {property_context['address']}")
            if property_context.get("owner"):
                context_parts.append(f"Owner: {property_context['owner']}")
            if property_context.get("land_use"):
                context_parts.append(f"Land Use: {property_context['land_use']}")
            if property_context.get("area_acres"):
                context_parts.append(f"Area: {property_context['area_acres']:.2f} acres")
            if context_parts:
                context_str = " | ".join(context_parts)
        
        system_prompt = """You are a commercial property analyst specializing in pavement and surface condition assessment. 

You analyze satellite imagery of properties to score them as potential leads for pavement maintenance, sealcoating, and repair services.

The image shows a property with a RED BOUNDARY LINE indicating the exact parcel boundaries. Focus your analysis on what's INSIDE this boundary.

Always respond with valid JSON only, no markdown formatting."""

        user_prompt = f"""{effective_prompt}

Property context: {context_str}

Analyze the satellite image and respond with this exact JSON structure:
{{
    "lead_score": <number 0-100>,
    "confidence": <number 0-100 indicating how confident you are>,
    "reasoning": "<2-3 sentence explanation of why you gave this score>",
    "observations": {{
        "paved_area_pct": <estimated % of property that is paved>,
        "building_pct": <estimated % covered by buildings/roofs>,
        "landscaping_pct": <estimated % that is grass/trees/landscaping>,
        "condition": "<one of: excellent, good, fair, poor, critical>",
        "visible_issues": ["<list>", "<of>", "<observed issues>"]
    }}
}}"""

        try:
            logger.info(f"  [VLM] Sending image to {self.DEFAULT_MODEL} via OpenRouter...")
            
            response = await client.chat.completions.create(
                model=self.DEFAULT_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_base64}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=1000,
                temperature=0.3,  # Lower temperature for more consistent scoring
                extra_body={"usage": {"include": True}},  # Request usage/cost from OpenRouter
            )
            
            # Extract usage info from OpenRouter response
            usage_info = None
            if hasattr(response, 'usage') and response.usage:
                usage_info = VLMUsageInfo(
                    prompt_tokens=getattr(response.usage, 'prompt_tokens', 0) or 0,
                    completion_tokens=getattr(response.usage, 'completion_tokens', 0) or 0,
                    total_tokens=getattr(response.usage, 'total_tokens', 0) or 0,
                    cost=getattr(response.usage, 'cost', 0) or 0.0,
                )
                logger.info(f"  [VLM] Usage: {usage_info.total_tokens} tokens, ${usage_info.cost:.6f}")
            
            # Parse response
            content = response.choices[0].message.content
            logger.info(f"  [VLM] Raw response: {content[:200]}...")
            
            # Clean up response (remove markdown if present)
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            # Parse JSON
            data = json.loads(content)
            
            # Extract observations
            obs_data = data.get("observations", {})
            observations = VLMObservations(
                paved_area_pct=obs_data.get("paved_area_pct", 0),
                building_pct=obs_data.get("building_pct", 0),
                landscaping_pct=obs_data.get("landscaping_pct", 0),
                condition=obs_data.get("condition", "unknown"),
                visible_issues=obs_data.get("visible_issues", [])
            )
            
            result = VLMAnalysisResult(
                success=True,
                lead_score=int(data.get("lead_score", 0)),
                confidence=int(data.get("confidence", 0)),
                reasoning=data.get("reasoning", ""),
                observations=observations,
                raw_response=data,
                usage=usage_info,
            )
            
            logger.info(f"  [VLM] Analysis complete: score={result.lead_score}, confidence={result.confidence}%")
            logger.info(f"  [VLM] Reasoning: {result.reasoning}")
            if usage_info:
                logger.info(f"  [VLM] Cost: ${usage_info.cost:.6f} ({usage_info.total_tokens} tokens)")
            
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"  [VLM] Failed to parse response as JSON: {e}")
            return VLMAnalysisResult.from_error(f"Invalid JSON response: {e}")
        except Exception as e:
            logger.error(f"  [VLM] Analysis failed: {e}")
            return VLMAnalysisResult.from_error(str(e))


# Singleton instance
vlm_analysis_service = VLMAnalysisService()

