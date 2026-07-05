import { cn } from "./utils"

export function Progress({ value, className }: { value: number; className?: string }) {
  return (
    <div className={cn("relative h-2.5 w-full overflow-hidden rounded-full bg-slate-100", className)}>
      <div
        className="h-full rounded-full bg-primary transition-all"
        style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
      />
    </div>
  )
}
