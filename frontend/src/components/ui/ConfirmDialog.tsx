import { createPortal } from "react-dom"
import { X } from "lucide-react"

type ConfirmDialogProps = {
  open: boolean
  title: string
  description?: string
  confirmLabel?: string
  cancelLabel?: string
  danger?: boolean
  loading?: boolean
  onConfirm: () => void
  onCancel: () => void
}

export default function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "确认",
  cancelLabel = "取消",
  danger = false,
  loading = false,
  onConfirm,
  onCancel
}: ConfirmDialogProps) {
  if (!open) return null

  return createPortal(
    <div className="fixed inset-0 z-[10000] flex items-center justify-center">
      <div className="fixed inset-0 bg-black/40 backdrop-blur-sm" onClick={onCancel} />
      <div className="relative z-10 w-full max-w-[420px] rounded-2xl border border-[#e7e7e7] bg-white p-6 shadow-[0_20px_60px_rgba(15,23,42,0.18)]">
        <button
          type="button"
          onClick={onCancel}
          className="absolute right-4 top-4 flex h-7 w-7 items-center justify-center rounded-lg text-[#999] transition hover:bg-[#f4f4f4]"
        >
          <X className="h-4 w-4" />
        </button>

        <h3 className="text-lg font-semibold text-[#1f1f1f]">{title}</h3>
        {description && (
          <p className="mt-2 text-sm leading-6 text-[#666]">{description}</p>
        )}

        <div className="mt-6 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={loading}
            className="rounded-lg border border-[#ddd] px-4 py-2 text-sm text-[#555] transition hover:bg-[#f5f5f5] disabled:opacity-50"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={loading}
            className={`rounded-lg px-4 py-2 text-sm font-medium text-white transition disabled:opacity-50 ${
              danger
                ? "bg-red-500 hover:bg-red-600"
                : "bg-blue-600 hover:bg-blue-700"
            }`}
          >
            {loading ? "处理中..." : confirmLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body
  )
}
