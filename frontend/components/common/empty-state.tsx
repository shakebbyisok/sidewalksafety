import { ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface EmptyStateProps {
  title: string
  description?: string
  icon?: ReactNode
  action?: {
    label: string
    onClick: () => void
  }
  className?: string
}

export function EmptyState({
  title,
  description,
  icon,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div className={cn('flex flex-col items-center justify-center py-12 text-center', className)}>
      {icon && <div className="mb-4 text-muted-foreground/50">{icon}</div>}
      <h3 className="text-base font-semibold">{title}</h3>
      {description && (
        <p className="mt-1.5 text-[13px] text-muted-foreground max-w-sm">
          {description}
        </p>
      )}
      {action && (
        <Button className="mt-4" onClick={action.onClick}>
          {action.label}
        </Button>
      )}
    </div>
  )
}

