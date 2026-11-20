import { useState, type ReactNode } from "react";
import { Globe } from "lucide-react";
import { cn } from "../utils";
import { getAgentIconSrc, agentIconNeedsDarkInvert } from "../lib/agentIcons";

interface AgentIconProps {
  agentKey: string;
  displayName?: string;
  className?: string;
  imageClassName?: string;
  fallback?: ReactNode;
}

export function AgentIcon({
  agentKey,
  displayName,
  className,
  imageClassName,
  fallback,
}: AgentIconProps) {
  const src = getAgentIconSrc(agentKey);
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const hasFailed = src === failedSrc;

  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center overflow-hidden rounded-md border border-border-subtle bg-surface",
        className
      )}
      title={displayName}
      aria-hidden="true"
    >
      {src && !hasFailed ? (
        <img
          src={src}
          alt=""
          draggable={false}
          className={cn(
            "h-full w-full object-contain",
            agentIconNeedsDarkInvert(agentKey) && "dark:invert",
            imageClassName
          )}
          onError={() => setFailedSrc(src)}
        />
      ) : (
        fallback ?? <Globe className="h-1/2 w-1/2 text-muted" />
      )}
    </span>
  );
}
