'use client'

import { useState } from 'react'
import { useScrapeDeals } from '@/lib/queries/use-deals'
import { Button } from '@/components/ui/button'
import { InputField } from '@/components/common/form-field'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Search } from 'lucide-react'

export function ScrapeDealsForm() {
  const [open, setOpen] = useState(false)
  const [areaType, setAreaType] = useState<'zip' | 'county'>('zip')
  const [value, setValue] = useState('')
  const [state, setState] = useState('')
  const [maxDeals, setMaxDeals] = useState(50)

  const scrapeDeals = useScrapeDeals()

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    scrapeDeals.mutate(
      {
        area_type: areaType,
        value,
        state: areaType === 'county' ? state : undefined,
        max_deals: maxDeals,
      },
      {
        onSuccess: () => {
          setOpen(false)
          setValue('')
          setState('')
        },
      }
    )
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Search className="h-4 w-4 mr-2" />
          Scrape Deals
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Scrape Deals</DialogTitle>
          <DialogDescription>
            Find parking lot deals by zip code or county
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium">Search Type</label>
            <div className="flex gap-2">
              <Button
                type="button"
                variant={areaType === 'zip' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setAreaType('zip')}
              >
                Zip Code
              </Button>
              <Button
                type="button"
                variant={areaType === 'county' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setAreaType('county')}
              >
                County
              </Button>
            </div>
          </div>

          {areaType === 'zip' ? (
            <InputField
              label="Zip Code"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              required
              placeholder="12345"
            />
          ) : (
            <>
              <InputField
                label="County"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                required
                placeholder="Los Angeles"
              />
              <InputField
                label="State"
                value={state}
                onChange={(e) => setState(e.target.value)}
                required
                placeholder="CA"
              />
            </>
          )}

          <InputField
            label="Max Deals"
            type="number"
            value={maxDeals.toString()}
            onChange={(e) => setMaxDeals(parseInt(e.target.value) || 50)}
            min={1}
            max={200}
            helperText="Higher limits increase API costs (1-200)"
          />

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={scrapeDeals.isPending}>
              {scrapeDeals.isPending ? 'Scraping...' : 'Scrape'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

