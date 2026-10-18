import { clsx, type ClassValue } from "clsx"

// Class-name helper for the migrated GreenChain components (AIDTRACE has no tailwind-merge dependency).
export function cn(...inputs: ClassValue[]) {
  return clsx(inputs)
}
