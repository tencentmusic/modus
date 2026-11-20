import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

/** Shorten the user's home directory to `~` for display. Windows paths also
 *  get their separators unified: agent dirs are joined from `/`-separated
 *  relative paths, which reads as `~\.workbuddy/skills` otherwise (#495). */
export function compactHomePath(path: string) {
    const display = /^[A-Za-z]:\\/.test(path) ? path.replace(/\//g, "\\") : path;
    return display
        .replace(/^\/Users\/[^/]+/, "~")
        .replace(/^\/home\/[^/]+/, "~")
        .replace(/^[A-Za-z]:\\Users\\[^\\]+/, "~");
}
