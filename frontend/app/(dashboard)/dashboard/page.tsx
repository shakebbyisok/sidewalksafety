'use client'

import { useDeals } from '@/lib/queries/use-deals'
import { DealList } from '@/components/features/deals/deal-list'
import { ScrapeDealsForm } from '@/components/features/deals/scrape-deals-form'
import { useEvaluateDeal } from '@/lib/queries/use-evaluations'
import { useState } from 'react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

export default function DashboardPage() {
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined)
  const { data: deals, isLoading } = useDeals(statusFilter)
  const evaluateDeal = useEvaluateDeal()

  const handleEvaluate = (dealId: string) => {
    evaluateDeal.mutate(dealId)
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold">Deals</h2>
          <p className="text-sm text-muted-foreground mt-1">
            Manage and evaluate parking lot deals
          </p>
        </div>
        <ScrapeDealsForm />
      </div>

      <Tabs defaultValue="all" onValueChange={(value) => setStatusFilter(value === 'all' ? undefined : value)}>
        <TabsList>
          <TabsTrigger value="all">All</TabsTrigger>
          <TabsTrigger value="pending">Pending</TabsTrigger>
          <TabsTrigger value="evaluating">Evaluating</TabsTrigger>
          <TabsTrigger value="evaluated">Evaluated</TabsTrigger>
        </TabsList>
        <TabsContent value={statusFilter || 'all'} className="mt-4">
          <DealList
            deals={deals || []}
            isLoading={isLoading}
            onEvaluate={handleEvaluate}
          />
        </TabsContent>
      </Tabs>
    </div>
  )
}

