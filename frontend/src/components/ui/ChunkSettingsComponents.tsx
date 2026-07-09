import { useState } from "react"
import { ChevronDown } from "lucide-react"
import { cn } from "./utils"

export function Section({
  title,
  children,
  defaultOpen = true,
}: {
  title: string
  children: React.ReactNode
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="border-b border-[#f0f0f0] last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between py-3.5 text-left transition hover:bg-[#fafafa] rounded-lg px-1"
      >
        <span className="text-sm font-semibold text-[#1f1f1f]">{title}</span>
        <ChevronDown
          className={cn(
            "h-4 w-4 text-[#bbb] transition-transform duration-200",
            !open && "-rotate-90"
          )}
        />
      </button>
      {open && <div className="px-1 pb-5 pt-1">{children}</div>}
    </div>
  )
}

export function NumberInput({
  label,
  hint,
  value,
  onChange,
  min,
  max,
  disabled = false,
}: {
  label: string
  hint: string
  value: number
  onChange: (v: number) => void
  min?: number
  max?: number
  disabled?: boolean
}) {
  return (
    <div className="py-2">
      <label className="mb-1.5 block text-sm font-medium text-[#333]">{label}</label>
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(Number(e.target.value) || 0)}
        min={min}
        max={max}
        disabled={disabled}
        className="w-full rounded-lg border border-[#e5e5e5] bg-[#fafafa] px-3 py-2.5 text-sm text-[#1f1f1f] outline-none transition focus:border-blue-400 focus:bg-white focus:ring-2 focus:ring-blue-50 disabled:cursor-not-allowed disabled:text-[#aaa]"
      />
      <p className="mt-1.5 text-xs text-[#aaa]">{hint}</p>
    </div>
  )
}

export function TextInput({
  label,
  hint,
  value,
  onChange,
  placeholder,
  mono,
}: {
  label: string
  hint: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
  mono?: boolean
}) {
  return (
    <div className="py-2">
      <label className="mb-1.5 block text-sm font-medium text-[#333]">{label}</label>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={cn(
          "w-full rounded-lg border border-[#e5e5e5] bg-[#fafafa] px-3 py-2.5 text-sm text-[#1f1f1f] outline-none transition focus:border-blue-400 focus:bg-white focus:ring-2 focus:ring-blue-50",
          mono && "font-mono"
        )}
      />
      <p className="mt-1.5 text-xs text-[#aaa]">{hint}</p>
    </div>
  )
}

export function Toggle({
  label,
  hint,
  checked,
  onChange,
  disabled = false,
}: {
  label: string
  hint: string
  checked: boolean
  onChange: (v: boolean) => void
  disabled?: boolean
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-2.5">
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-[#333]">{label}</div>
        <p className="mt-0.5 text-xs text-[#aaa] leading-relaxed">{hint}</p>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn(
          "relative inline-flex h-[22px] w-[42px] shrink-0 items-center rounded-full transition-colors duration-200 disabled:cursor-not-allowed disabled:opacity-50",
          checked ? "bg-blue-500" : "bg-[#e0e0e0]"
        )}
      >
        <span
          className={cn(
            "inline-block h-[18px] w-[18px] rounded-full bg-white shadow-[0_1px_3px_rgba(0,0,0,0.15)] transition-transform duration-200",
            checked ? "translate-x-[22px]" : "translate-x-[2px]"
          )}
        />
      </button>
    </div>
  )
}

export function RadioGroup({
  label,
  hint,
  options,
  value,
  onChange,
}: {
  label: string
  hint: string
  options: { value: string; label: string; disabled?: boolean }[]
  value: string
  onChange: (v: string) => void
}) {
  return (
    <div className="py-2">
      <div className="mb-2.5">
        <div className="text-sm font-medium text-[#333]">{label}</div>
        <p className="text-xs text-[#aaa]">{hint}</p>
      </div>
      <div className="flex flex-wrap gap-2">
        {options.map((opt) => (
          <button
            key={opt.value}
            type="button"
            disabled={opt.disabled}
            onClick={() => onChange(opt.value)}
            className={cn(
              "rounded-lg border px-3.5 py-1.5 text-sm font-medium transition-all duration-150 disabled:cursor-not-allowed disabled:opacity-50",
              value === opt.value
                ? "border-blue-500 bg-blue-500 text-white shadow-sm"
                : "border-[#e5e5e5] bg-white text-[#555] hover:border-[#ccc] hover:bg-[#fafafa]"
            )}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  )
}
