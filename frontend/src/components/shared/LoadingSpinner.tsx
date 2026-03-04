import { cn } from '@/lib/utils'

interface LoadingSpinnerProps {
  className?: string
  size?: 'sm' | 'md' | 'lg'
  fullPage?: boolean
}

export function LoadingSpinner({ className, size = 'md', fullPage = false }: LoadingSpinnerProps) {
  const sizeClasses = {
    sm: 'h-4 w-4 border-2',
    md: 'h-8 w-8 border-2',
    lg: 'h-12 w-12 border-4',
  }

  const spinner = (
    <div
      className={cn(
        'animate-spin rounded-full border-muted border-t-primary',
        sizeClasses[size],
        className
      )}
      role="status"
      aria-label="Loading"
    />
  )

  if (fullPage) {
    return (
      <div className="flex h-full w-full items-center justify-center min-h-[200px]">
        {spinner}
      </div>
    )
  }

  return spinner
}
