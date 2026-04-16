import { cn } from "@/lib/utils";

/**
 * aiRA sparkle icon — the brand icon used for the AI assistant.
 * Renders inline SVG so it inherits className for sizing and color.
 */
export function AiraIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 14 14"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={cn("h-4 w-4", className)}
    >
      <path
        d="m11.454 5.0909 0.7955-1.75 1.75-0.79546-1.75-0.79545-0.7955-1.75-0.7954 1.75-1.75 0.79545 1.75 0.79546zm-4.7727 0.31818-1.5909-3.5-1.5909 3.5-3.5 1.5909 3.5 1.5909 1.5909 3.5 1.5909-3.5 3.5-1.5909zm4.7727 3.5-0.7954 1.75-1.75 0.7954 1.75 0.7955 0.7954 1.75 0.7955-1.75 1.75-0.7955-1.75-0.7954z"
        fill="url(#aira-gradient)"
      />
      <defs>
        <linearGradient
          id="aira-gradient"
          x1="2.8636"
          x2="17.182"
          y1="0"
          y2="0"
          gradientUnits="userSpaceOnUse"
        >
          <stop stopColor="#6268FF" offset=".255" />
          <stop stopColor="#3BA7FF" offset="1" />
        </linearGradient>
      </defs>
    </svg>
  );
}

/**
 * aiRA logo mark — larger version with centered sparkle, used on login/splash screens.
 * Uses currentColor so it matches any background (pass text-white, text-primary, etc. via className).
 */
export function AiraLogo({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={cn("h-12 w-12", className)}
    >
      <path
        d="M15.5 10.5L16.125 9.125L17.5 8.5L16.125 7.875L15.5 6.5L14.875 7.875L13.5 8.5L14.875 9.125L15.5 10.5Z
           M11.75 10.75L10.5 8L9.25 10.75L6.5 12L9.25 13.25L10.5 16L11.75 13.25L14.5 12L11.75 10.75Z
           M15.5 13.5L14.875 14.875L13.5 15.5L14.875 16.125L15.5 17.5L16.125 16.125L17.5 15.5L16.125 14.875L15.5 13.5Z"
        fill="currentColor"
      />
    </svg>
  );
}
