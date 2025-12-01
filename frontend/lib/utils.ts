import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatCurrency(amount: string | number): string {
  const num = typeof amount === 'string' ? parseFloat(amount) : amount
  if (isNaN(num)) return '$0.00'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(num)
}

export function formatDate(date: string | Date): string {
  const d = typeof date === 'string' ? new Date(date) : date
  return new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(d)
}

export function formatDateTime(date: string | Date): string {
  const d = typeof date === 'string' ? new Date(date) : date
  return new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(d)
}

export function formatNumber(num: number, decimals: number = 0): string {
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(num)
}

export function getStatusColor(status: string): string {
  switch (status) {
    case 'evaluated':
      return 'bg-green-500/10 text-green-600 dark:text-green-400'
    case 'evaluating':
      return 'bg-yellow-500/10 text-yellow-600 dark:text-yellow-400'
    case 'pending':
      return 'bg-gray-500/10 text-gray-600 dark:text-gray-400'
    case 'archived':
      return 'bg-gray-500/10 text-gray-500 dark:text-gray-500'
    default:
      return 'bg-gray-500/10 text-gray-600 dark:text-gray-400'
  }
}

export function getDamageSeverityColor(severity?: string): string {
  switch (severity) {
    case 'critical':
      return 'bg-red-500/10 text-red-600 dark:text-red-400'
    case 'high':
      return 'bg-orange-500/10 text-orange-600 dark:text-orange-400'
    case 'medium':
      return 'bg-yellow-500/10 text-yellow-600 dark:text-yellow-400'
    case 'low':
      return 'bg-green-500/10 text-green-600 dark:text-green-400'
    default:
      return 'bg-gray-500/10 text-gray-600 dark:text-gray-400'
  }
}

