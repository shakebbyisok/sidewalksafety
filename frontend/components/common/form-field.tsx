import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'

interface InputFieldProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label: string
  error?: string
  required?: boolean
}

export function InputField({
  label,
  error,
  required,
  className,
  id,
  ...props
}: InputFieldProps) {
  const fieldId = id || `field-${label.toLowerCase().replace(/\s+/g, '-')}`

  return (
    <div className="space-y-2">
      <Label htmlFor={fieldId}>
        {label}
        {required && <span className="text-destructive ml-1">*</span>}
      </Label>
      <Input
        id={fieldId}
        error={!!error}
        helperText={error}
        className={className}
        {...props}
      />
    </div>
  )
}

