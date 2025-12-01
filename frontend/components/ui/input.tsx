import * as React from 'react'
import { cn } from '@/lib/utils'

export interface InputProps
  extends React.InputHTMLAttributes<HTMLInputElement> {
  error?: boolean
  helperText?: string
}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, error, helperText, ...props }, ref) => {
    return (
      <div className="w-full">
        <input
          type={type}
          className={cn(
            'flex h-10 w-full bg-background px-4 py-2 text-sm font-medium transition-all rounded-[var(--radius)]',
            'border file:border-0 file:bg-transparent file:text-sm file:font-medium',
            'placeholder:text-muted-foreground/60',
            'disabled:cursor-not-allowed disabled:opacity-50',
            error
              ? 'border-destructive/50 hover:border-destructive/60 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-destructive/15 focus-visible:border-destructive/60'
              : 'border-border/30 hover:border-primary/40 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary/15 focus-visible:border-primary/60',
            className
          )}
          ref={ref}
          {...props}
        />
        {helperText && (
          <p className={cn(
            'mt-1.5 text-xs',
            error ? 'text-destructive' : 'text-muted-foreground'
          )}>
            {helperText}
          </p>
        )}
      </div>
    )
  }
)
Input.displayName = 'Input'

export { Input }

