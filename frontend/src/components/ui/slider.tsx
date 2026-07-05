import * as React from "react"
import { cn } from "./utils"

export function Slider({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input type="range" className={cn("w-full accent-blue-600", className)} {...props} />
}
