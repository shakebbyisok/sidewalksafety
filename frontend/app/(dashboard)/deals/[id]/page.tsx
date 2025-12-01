'use client'

import { useDealWithEvaluation } from '@/lib/queries/use-evaluations'
import { useEvaluateDeal } from '@/lib/queries/use-evaluations'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { getStatusColor, getDamageSeverityColor, formatCurrency, formatNumber } from '@/lib/utils'
import { MapPin, Building2, DollarSign, TrendingUp, AlertTriangle } from 'lucide-react'
import { useParams } from 'next/navigation'

export default function DealDetailPage() {
  const params = useParams()
  const dealId = params.id as string
  const { data: deal, isLoading } = useDealWithEvaluation(dealId)
  const evaluateDeal = useEvaluateDeal()

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }

  if (!deal) {
    return <div>Deal not found</div>
  }

  const evaluation = deal.evaluation

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold">{deal.business_name}</h2>
        <p className="text-sm text-muted-foreground mt-1">{deal.address}</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Deal Information</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center gap-2">
              <MapPin className="h-4 w-4 text-muted-foreground" />
              <div>
                <p className="text-sm font-medium">Address</p>
                <p className="text-xs text-muted-foreground">{deal.address}</p>
              </div>
            </div>
            {deal.city && deal.state && (
              <div className="flex items-center gap-2">
                <Building2 className="h-4 w-4 text-muted-foreground" />
                <div>
                  <p className="text-sm font-medium">Location</p>
                  <p className="text-xs text-muted-foreground">
                    {deal.city}, {deal.state} {deal.zip}
                  </p>
                </div>
              </div>
            )}
            <div>
              <p className="text-sm font-medium">Status</p>
              <Badge className={getStatusColor(deal.status)}>
                {deal.status}
              </Badge>
            </div>
            {deal.category && (
              <div>
                <p className="text-sm font-medium">Category</p>
                <p className="text-xs text-muted-foreground">{deal.category}</p>
              </div>
            )}
            {!evaluation && deal.status === 'pending' && (
              <Button
                onClick={() => evaluateDeal.mutate(dealId)}
                disabled={evaluateDeal.isPending}
                className="w-full mt-4"
              >
                {evaluateDeal.isPending ? 'Evaluating...' : 'Evaluate Deal'}
              </Button>
            )}
          </CardContent>
        </Card>

        {evaluation && (
          <Card>
            <CardHeader>
              <CardTitle>Evaluation Results</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {evaluation.deal_score !== null && evaluation.deal_score !== undefined && (
                <div>
                  <p className="text-sm font-medium">Deal Score</p>
                  <p className="text-2xl font-semibold">
                    {formatNumber(evaluation.deal_score, 1)}/10
                  </p>
                </div>
              )}
              {evaluation.damage_severity && (
                <div>
                  <p className="text-sm font-medium">Damage Severity</p>
                  <Badge className={getDamageSeverityColor(evaluation.damage_severity)}>
                    {evaluation.damage_severity}
                  </Badge>
                </div>
              )}
              {evaluation.parking_lot_area_sqft && (
                <div className="flex items-center gap-2">
                  <TrendingUp className="h-4 w-4 text-muted-foreground" />
                  <div>
                    <p className="text-sm font-medium">Parking Lot Area</p>
                    <p className="text-xs text-muted-foreground">
                      {formatNumber(evaluation.parking_lot_area_sqft, 0)} sq ft
                    </p>
                  </div>
                </div>
              )}
              {evaluation.estimated_job_value && (
                <div className="flex items-center gap-2">
                  <DollarSign className="h-4 w-4 text-muted-foreground" />
                  <div>
                    <p className="text-sm font-medium">Estimated Job Value</p>
                    <p className="text-xs text-muted-foreground">
                      {formatCurrency(evaluation.estimated_job_value)}
                    </p>
                  </div>
                </div>
              )}
              {evaluation.estimated_repair_cost && (
                <div className="flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 text-muted-foreground" />
                  <div>
                    <p className="text-sm font-medium">Estimated Repair Cost</p>
                    <p className="text-xs text-muted-foreground">
                      {formatCurrency(evaluation.estimated_repair_cost)}
                    </p>
                  </div>
                </div>
              )}
              {evaluation.crack_density_percent !== null && evaluation.crack_density_percent !== undefined && (
                <div>
                  <p className="text-sm font-medium">Crack Density</p>
                  <p className="text-xs text-muted-foreground">
                    {formatNumber(evaluation.crack_density_percent, 1)}%
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}

