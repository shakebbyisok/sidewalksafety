'use client'

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiClient } from '@/lib/api/client'
import { cn } from '@/lib/utils'
import { 
  Activity,
  RefreshCw,
  Zap,
  DollarSign,
  Clock,
  TrendingUp,
  Globe,
  MapPin,
  Brain,
  Layers,
  Building2,
  Search,
  BarChart3,
  Sparkles,
  Map,
  FileText,
} from 'lucide-react'

interface UsageSummary {
  period_days: number
  total_requests: number
  total_cost_usd: number
  total_tokens: number
  by_service: Record<string, { count: number; total_cost: number; total_tokens: number }>
}

interface DailyUsage {
  date: string
  request_count: number
  total_cost_usd: number
  total_tokens: number
}

// Service metadata - reflecting our actual current services and billing
const SERVICE_META: Record<string, { label: string; icon: typeof Globe; description: string; color: string; billing: string }> = {
  regrid: { 
    label: 'Regrid', 
    icon: FileText, 
    description: 'Property parcel lookups',
    color: 'bg-emerald-500',
    billing: 'Subscription (quota)'
  },
  google_satellite: { 
    label: 'Satellite Tiles', 
    icon: Map, 
    description: 'Raw tile server (free)',
    color: 'bg-sky-500',
    billing: 'Free'
  },
  google_places: { 
    label: 'Places API', 
    icon: Building2, 
    description: 'Business discovery',
    color: 'bg-amber-500',
    billing: '~$20/1K ($200 free/mo)'
  },
  openrouter: { 
    label: 'OpenRouter VLM', 
    icon: Brain, 
    description: 'AI property analysis',
    color: 'bg-violet-500',
    billing: 'Per-token (actual cost)'
  },
  vlm_analysis: { 
    label: 'VLM Analysis', 
    icon: Brain, 
    description: 'AI property analysis',
    color: 'bg-violet-500',
    billing: 'Per-token'
  },
  discovery_pipeline: { 
    label: 'Discovery Jobs', 
    icon: Search, 
    description: 'Complete discovery runs',
    color: 'bg-stone-500',
    billing: 'Aggregated'
  },
}

const PERIOD_OPTIONS = [
  { value: 7, label: '7 days' },
  { value: 14, label: '14 days' },
  { value: 30, label: '30 days' },
  { value: 90, label: '90 days' },
]

export default function UsagePage() {
  const [days, setDays] = useState(30)

  const { data: summary, isLoading, refetch, isFetching } = useQuery<UsageSummary>({
    queryKey: ['usage-summary', days],
    queryFn: async () => (await apiClient.get(`/usage/summary?days=${days}`)).data,
  })

  const { data: daily } = useQuery<DailyUsage[]>({
    queryKey: ['usage-daily', Math.min(days, 30)],
    queryFn: async () => (await apiClient.get(`/usage/daily?days=${Math.min(days, 30)}`)).data,
  })

  const formatCost = (n: number) => {
    if (n === 0) return '$0.00'
    if (n < 0.01) return `$${n.toFixed(4)}`
    return `$${n.toFixed(2)}`
  }

  // Calculate max for bar chart scaling
  const maxRequests = Math.max(...(daily?.map(d => d.request_count) || [1]))

  return (
    <div className="min-h-full bg-stone-100 p-6">
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-stone-800">Usage</h1>
            <p className="text-sm text-stone-500 mt-0.5">API consumption and estimated costs</p>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              className="h-8 px-2 text-xs font-medium bg-white border border-stone-200 rounded-lg text-stone-600 focus:outline-none focus:ring-2 focus:ring-stone-300"
            >
              {PERIOD_OPTIONS.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
            <button
              onClick={() => refetch()}
              disabled={isFetching}
              className="h-8 w-8 flex items-center justify-center bg-white border border-stone-200 rounded-lg hover:bg-stone-50 transition-colors disabled:opacity-50"
            >
              <RefreshCw className={cn('h-3.5 w-3.5 text-stone-500', isFetching && 'animate-spin')} />
            </button>
          </div>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center h-64">
            <div className="flex flex-col items-center gap-2">
              <div className="h-6 w-6 border-2 border-stone-300 border-t-stone-600 rounded-full animate-spin" />
              <span className="text-xs text-stone-500">Loading usage data...</span>
            </div>
          </div>
        ) : !summary || summary.total_requests === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 bg-white rounded-xl border border-stone-200">
            <div className="w-12 h-12 rounded-xl bg-stone-100 flex items-center justify-center mb-3">
              <Activity className="h-5 w-5 text-stone-400" />
            </div>
            <p className="text-sm font-medium text-stone-600">No usage data</p>
            <p className="text-xs text-stone-400 mt-1">Run a discovery to see metrics</p>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Stats Grid */}
            <div className="grid grid-cols-4 gap-4">
              <StatCard 
                label="Total Requests" 
                value={summary.total_requests.toLocaleString()}
                icon={Zap}
                iconColor="text-amber-500"
              />
              <StatCard 
                label="Estimated Cost" 
                value={formatCost(summary.total_cost_usd)}
                sub={`${formatCost(summary.total_cost_usd / days)}/day avg`}
                icon={DollarSign}
                iconColor="text-emerald-500"
              />
              <StatCard 
                label="AI Tokens" 
                value={summary.total_tokens.toLocaleString()}
                icon={Sparkles}
                iconColor="text-violet-500"
              />
              <StatCard 
                label="Period" 
                value={`${days} days`}
                icon={Clock}
                iconColor="text-sky-500"
              />
            </div>

            {/* Charts Row */}
            <div className="grid grid-cols-3 gap-4">
              {/* Daily Activity Chart */}
              <div className="col-span-2 bg-white rounded-xl border border-stone-200 p-4">
                <div className="flex items-center gap-2 mb-4">
                  <div className="w-6 h-6 rounded bg-stone-100 flex items-center justify-center">
                    <BarChart3 className="h-3.5 w-3.5 text-stone-500" />
                  </div>
                  <span className="text-xs font-semibold text-stone-600">Daily Activity</span>
                </div>
                {daily && daily.length > 0 ? (
                  <div className="flex items-end gap-1 h-32">
                    {daily.slice(-14).map((d, i) => {
                      const height = (d.request_count / maxRequests) * 100
                      return (
                        <div key={d.date} className="flex-1 flex flex-col items-center gap-1">
                          <div 
                            className="w-full bg-stone-800 rounded-sm transition-all hover:bg-stone-700"
                            style={{ height: `${Math.max(height, 4)}%` }}
                            title={`${d.request_count} requests on ${d.date}`}
                          />
                          {i % 2 === 0 && (
                            <span className="text-[9px] text-stone-400 tabular-nums">
                              {new Date(d.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                            </span>
                          )}
                        </div>
                      )
                    })}
                  </div>
                ) : (
                  <div className="h-32 flex items-center justify-center text-xs text-stone-400">
                    No activity data
                  </div>
                )}
              </div>

              {/* Service Distribution */}
              <div className="bg-white rounded-xl border border-stone-200 p-4">
                <div className="flex items-center gap-2 mb-4">
                  <div className="w-6 h-6 rounded bg-stone-100 flex items-center justify-center">
                    <Layers className="h-3.5 w-3.5 text-stone-500" />
                  </div>
                  <span className="text-xs font-semibold text-stone-600">By Service</span>
                </div>
                <div className="space-y-2">
                  {Object.entries(summary.by_service)
                    .sort((a, b) => b[1].count - a[1].count)
                    .slice(0, 5)
                    .map(([service, data]) => {
                      const meta = SERVICE_META[service] || { label: service, icon: Globe, color: 'bg-stone-400' }
                      const pct = (data.count / summary.total_requests) * 100
                      return (
                        <div key={service} className="space-y-1">
                          <div className="flex items-center justify-between text-xs">
                            <span className="text-stone-600 font-medium">{meta.label}</span>
                            <span className="text-stone-400 tabular-nums">{data.count}</span>
                          </div>
                          <div className="h-1.5 bg-stone-100 rounded-full overflow-hidden">
                            <div 
                              className={cn('h-full rounded-full transition-all', meta.color)}
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                        </div>
                      )
                    })}
                </div>
              </div>
            </div>

            {/* Service Breakdown */}
            <div className="bg-white rounded-xl border border-stone-200 overflow-hidden">
              <div className="px-4 py-3 border-b border-stone-100 flex items-center gap-2">
                <div className="w-6 h-6 rounded bg-stone-100 flex items-center justify-center">
                  <Activity className="h-3.5 w-3.5 text-stone-500" />
                </div>
                <span className="text-xs font-semibold text-stone-600">Service Breakdown</span>
              </div>
              <div className="divide-y divide-stone-100">
                {Object.entries(summary.by_service)
                  .sort((a, b) => b[1].count - a[1].count)
                  .map(([service, data]) => {
                    const meta = SERVICE_META[service] || { 
                      label: service, 
                      icon: Globe, 
                      description: 'API service',
                      color: 'bg-stone-400',
                      billing: 'Unknown'
                    }
                    const Icon = meta.icon
                    const hasCost = data.total_cost > 0
                    return (
                      <div key={service} className="flex items-center justify-between px-4 py-3 hover:bg-stone-50 transition-colors">
                        <div className="flex items-center gap-3">
                          <div className={cn('w-8 h-8 rounded-lg flex items-center justify-center', meta.color.replace('bg-', 'bg-') + '/10')}>
                            <Icon className={cn('h-4 w-4', meta.color.replace('bg-', 'text-'))} />
                          </div>
                          <div>
                            <p className="text-sm font-medium text-stone-700">{meta.label}</p>
                            <p className="text-[11px] text-stone-400">{meta.billing}</p>
                          </div>
                        </div>
                        <div className="text-right">
                          <p className="text-sm font-semibold text-stone-700 tabular-nums">{data.count.toLocaleString()} calls</p>
                          {hasCost ? (
                            <p className="text-[11px] text-amber-600 tabular-nums">{formatCost(data.total_cost)}</p>
                          ) : (
                            <p className="text-[11px] text-emerald-600">Free / Quota</p>
                          )}
                        </div>
                      </div>
                    )
                  })}
              </div>
            </div>

            {/* Billing Notes Footer */}
            <div className="bg-stone-50 rounded-lg p-3 space-y-1.5">
              <p className="text-xs font-medium text-stone-600 flex items-center gap-1.5">
                <TrendingUp className="h-3 w-3" />
                Billing Notes
              </p>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px] text-stone-500">
                <span><span className="text-violet-600">•</span> OpenRouter: Actual per-token cost</span>
                <span><span className="text-amber-600">•</span> Places: ~$20/1K ($200 free/mo)</span>
                <span><span className="text-emerald-600">•</span> Regrid: Subscription quota</span>
                <span><span className="text-sky-600">•</span> Satellite: Free (raw tiles)</span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function StatCard({ 
  label, 
  value, 
  sub, 
  icon: Icon,
  iconColor = 'text-stone-500'
}: { 
  label: string
  value: string
  sub?: string
  icon: typeof Zap
  iconColor?: string
}) {
  return (
    <div className="bg-white rounded-xl border border-stone-200 p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-stone-500">{label}</span>
        <div className="w-6 h-6 rounded bg-stone-100 flex items-center justify-center">
          <Icon className={cn('h-3.5 w-3.5', iconColor)} />
        </div>
      </div>
      <p className="text-xl font-bold text-stone-800 tabular-nums">{value}</p>
      {sub && <p className="text-[11px] text-stone-400 mt-0.5">{sub}</p>}
    </div>
  )
}
