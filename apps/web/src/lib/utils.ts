import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function toBase64(text: string): string {
  return btoa(unescape(encodeURIComponent(text)));
}

export function fromBase64(encoded: string): string {
  return decodeURIComponent(escape(atob(encoded)));
}
