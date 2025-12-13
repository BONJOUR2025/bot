import * as React from "react";

import { cn } from "@/lib/utils";

const badgeVariants = {
  default: "inline-flex items-center rounded-full border border-transparent bg-primary px-3 py-1 text-xs font-semibold text-primary-foreground transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  secondary:
    "inline-flex items-center rounded-full border border-transparent bg-secondary px-3 py-1 text-xs font-semibold text-secondary-foreground transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  destructive:
    "inline-flex items-center rounded-full border border-transparent bg-destructive px-3 py-1 text-xs font-semibold text-destructive-foreground transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  outline:
    "inline-flex items-center rounded-full border border-border px-3 py-1 text-xs font-semibold text-foreground transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
};

function Badge({ className, variant = "default", ...props }) {
  return <div className={cn(badgeVariants[variant], className)} {...props} />;
}

export { Badge };
