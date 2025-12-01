import { Deal } from '@/types'
import { DealCard } from './deal-card'
import { EmptyState } from '@/components/common/empty-state'
import { ListSkeleton } from '@/components/common/loading-skeleton'
import { Package } from 'lucide-react'

interface DealListProps {
  deals: Deal[]
  isLoading?: boolean
  onEvaluate?: (id: string) => void
}

export function DealList({ deals, isLoading, onEvaluate }: DealListProps) {
  if (isLoading) {
    return <ListSkeleton items={5} />
  }

  if (!deals || deals.length === 0) {
    return (
      <EmptyState
        title="No deals found"
        description="Start by scraping deals for a zip code or county"
        icon={<Package className="h-10 w-10" />}
      />
    )
  }

  return (
    <div className="grid gap-3">
      {deals.map((deal) => (
        <DealCard key={deal.id} deal={deal} onEvaluate={onEvaluate} />
      ))}
    </div>
  )
}

