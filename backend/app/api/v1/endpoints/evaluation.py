from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
from pydantic import BaseModel
from app.db.base import get_db
from app.models.deal import Deal
from app.models.user import User
from app.models.evaluation import Evaluation
from app.schemas.evaluation import EvaluationResponse, DealWithEvaluation
from app.core.evaluator_service import evaluator_service
from app.core.dependencies import get_current_user

router = APIRouter()


class BatchEvaluateRequest(BaseModel):
    deal_ids: List[UUID]


class BatchEvaluateResponse(BaseModel):
    evaluated: int
    failed: int
    message: str


@router.post("/{deal_id}", response_model=EvaluationResponse, status_code=status.HTTP_201_CREATED)
async def evaluate_deal(
    deal_id: UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Evaluate a deal."""
    deal = db.query(Deal).filter(Deal.id == deal_id, Deal.user_id == current_user.id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    
    if deal.evaluation:
        return deal.evaluation
    
    if not deal.latitude or not deal.longitude:
        raise HTTPException(status_code=400, detail="Deal missing coordinates")
    
    deal.status = "evaluating"
    db.commit()
    
    # Run evaluation
    result = await evaluator_service.evaluate_deal(
        deal.address,
        float(deal.latitude),
        float(deal.longitude)
    )
    
    if "error" in result:
        deal.status = "pending"
        db.commit()
        raise HTTPException(status_code=500, detail=result["error"])
    
    # Save evaluation
    evaluation = Evaluation(
        deal_id=deal.id,
        deal_score=result.get("deal_score"),
        parking_lot_area_sqft=result.get("parking_lot_area_sqft"),
        crack_density_percent=result.get("crack_density_percent"),
        damage_severity=result.get("damage_severity"),
        estimated_repair_cost=result.get("estimated_repair_cost"),
        estimated_job_value=result.get("estimated_job_value"),
        satellite_image_url=result.get("satellite_image_url"),
        parking_lot_mask=result.get("parking_lot_mask"),
        crack_detections=result.get("crack_detections"),
        evaluation_metadata=result.get("evaluation_metadata"),
    )
    
    db.add(evaluation)
    deal.status = "evaluated"
    db.commit()
    db.refresh(evaluation)
    
    return evaluation


@router.post("/batch", response_model=BatchEvaluateResponse)
async def batch_evaluate_deals(
    request: BatchEvaluateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Evaluate multiple deals at once."""
    evaluated_count = 0
    failed_count = 0
    
    for deal_id in request.deal_ids:
        try:
            deal = db.query(Deal).filter(Deal.id == deal_id, Deal.user_id == current_user.id).first()
            if not deal:
                failed_count += 1
                continue
            
            # Skip if already evaluated
            if deal.evaluation:
                evaluated_count += 1
                continue
            
            if not deal.latitude or not deal.longitude:
                failed_count += 1
                continue
            
            deal.status = "evaluating"
            db.commit()
            
            # Run evaluation
            result = await evaluator_service.evaluate_deal(
                deal.address,
                float(deal.latitude),
                float(deal.longitude)
            )
            
            if "error" in result:
                deal.status = "pending"
                db.commit()
                failed_count += 1
                continue
            
            # Save evaluation
            evaluation = Evaluation(
                deal_id=deal.id,
                deal_score=result.get("deal_score"),
                parking_lot_area_sqft=result.get("parking_lot_area_sqft"),
                crack_density_percent=result.get("crack_density_percent"),
                damage_severity=result.get("damage_severity"),
                estimated_repair_cost=result.get("estimated_repair_cost"),
                estimated_job_value=result.get("estimated_job_value"),
                satellite_image_url=result.get("satellite_image_url"),
                parking_lot_mask=result.get("parking_lot_mask"),
                crack_detections=result.get("crack_detections"),
                evaluation_metadata=result.get("evaluation_metadata"),
            )
            
            db.add(evaluation)
            deal.status = "evaluated"
            db.commit()
            evaluated_count += 1
            
        except Exception as e:
            failed_count += 1
            # Rollback if needed
            db.rollback()
            continue
    
    return BatchEvaluateResponse(
        evaluated=evaluated_count,
        failed=failed_count,
        message=f"Evaluated {evaluated_count} deals, {failed_count} failed"
    )


@router.get("/{deal_id}", response_model=DealWithEvaluation)
def get_deal_with_evaluation(
    deal_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get deal with evaluation."""
    deal = db.query(Deal).filter(Deal.id == deal_id, Deal.user_id == current_user.id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    
    return deal

