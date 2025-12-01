import { Deal } from '@/types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { getStatusColor } from '@/lib/utils'
import { MapPin, Building2, ExternalLink } from 'lucide-react'
import Link from 'next/link'

interface DealCardProps {
  deal: Deal
  onEvaluate?: (id: string) => void
  showActions?: boolean
}

export function DealCard({ deal, onEvaluate, showActions = true }: DealCardProps) {
  return (
    <Card className="hover:shadow-md transition-shadow">
      <CardHeader>
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <CardTitle className="text-base">{deal.business_name}</CardTitle>
            <div className="flex items-center gap-2 mt-1.5">
              <MapPin className="h-3.5 w-3.5 text-muted-foreground" />
              <p className="text-xs text-muted-foreground">{deal.address}</p>
            </div>
          </div>
          <Badge className={getStatusColor(deal.status)}>
            {deal.status}
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          {deal.city && deal.state && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Building2 className="h-3.5 w-3.5" />
              <span>
                {deal.city}, {deal.state} {deal.zip}
              </span>
            </div>
          )}
          {deal.category && (
            <div className="text-xs text-muted-foreground">
              Category: {deal.category}
            </div>
          )}
          {showActions && (
            <div className="flex items-center gap-2 pt-2">
              <Link href={`/deals/${deal.id}`}>
                <Button variant="outline" size="sm">
                  View Details
                </Button>
              </Link>
              {onEvaluate && deal.status === 'pending' && (
                <Button
                  size="sm"
                  onClick={() => onEvaluate(deal.id)}
                >
                  Evaluate
                </Button>
              )}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

