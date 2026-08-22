import type { ReactNode } from "react";
import { createElement, Fragment } from "react";

const CLAUSE_RE = /\[\[([A-Z][A-Z0-9]+(?:-[A-Z0-9]+)*)\]\]/g;
const SHA_RE = /\b([0-9a-f]{7,40})\b/gi;
const INTENT_MARK = "⟦INTENT⟧";
const INTENT_END = "⟦/INTENT⟧";

export type ColorizeMode = "workbench" | "overview";

/**
 * Highlight prompt text:
 * - workbench: clause (blue) + context SHA (purple) — never yellow intent
 * - overview: also yellow intent spans wrapped by INTENT markers
 */
export function colorizePrompt(
  text: string,
  mode: ColorizeMode,
  onClauseClick?: (id: string) => void,
): ReactNode {
  if (!text) return null;

  type Part = { kind: "text" | "clause" | "ctx" | "intent"; value: string };
  const parts: Part[] = [];

  const pushText = (raw: string, allowIntent: boolean) => {
    if (!raw) return;
    if (allowIntent && raw.includes(INTENT_MARK)) {
      let rest = raw;
      while (rest.length) {
        const start = rest.indexOf(INTENT_MARK);
        if (start < 0) {
          tokenize(rest, parts);
          break;
        }
        tokenize(rest.slice(0, start), parts);
        rest = rest.slice(start + INTENT_MARK.length);
        const end = rest.indexOf(INTENT_END);
        if (end < 0) {
          parts.push({ kind: "intent", value: rest });
          break;
        }
        parts.push({ kind: "intent", value: rest.slice(0, end) });
        rest = rest.slice(end + INTENT_END.length);
      }
      return;
    }
    tokenize(raw, parts);
  };

  pushText(text, mode === "overview");

  return createElement(
    Fragment,
    null,
    ...parts.map((part, index) => {
      if (part.kind === "clause") {
        return createElement(
          "mark",
          {
            key: index,
            className: "mk-cl",
            onClick: onClauseClick ? () => onClauseClick(part.value) : undefined,
            title: part.value,
          },
          `[[${part.value}]]`,
        );
      }
      if (part.kind === "ctx") {
        return createElement("mark", { key: index, className: "mk-ctx" }, part.value);
      }
      if (part.kind === "intent") {
        return createElement("mark", { key: index, className: "mk-intent" }, part.value);
      }
      return createElement(Fragment, { key: index }, part.value);
    }),
  );
}

function tokenize(raw: string, parts: Part[]): void {
  if (!raw) return;
  let last = 0;
  const combined = new RegExp(`${CLAUSE_RE.source}|${SHA_RE.source}`, "gi");
  let match: RegExpExecArray | null;
  while ((match = combined.exec(raw)) !== null) {
    if (match.index > last) {
      parts.push({ kind: "text", value: raw.slice(last, match.index) });
    }
    if (match[1]) {
      parts.push({ kind: "clause", value: match[1] });
    } else if (match[2]) {
      parts.push({ kind: "ctx", value: match[2] });
    }
    last = match.index + match[0].length;
  }
  if (last < raw.length) {
    parts.push({ kind: "text", value: raw.slice(last) });
  }
}

type Part = { kind: "text" | "clause" | "ctx" | "intent"; value: string };

/** Wrap user intent for overview proposal prompts. */
export function wrapIntent(intent: string): string {
  return `${INTENT_MARK}${intent}${INTENT_END}`;
}

export function buildOverviewProposalPrompt(intent: string, head?: string): string {
  const wrapped = wrapIntent(intent.trim());
  return [
    "# 产品提案工单（Overview → spec/open/）",
    "",
    "## 用户意图",
    wrapped,
    "",
    "## 任务契约（已冻结于产品提案路径）",
    "- track: 由意图判定（默认 poc；明确合入主线才 promote）",
    "- 落点: `spec/open/proposal-*.md`（产品提案，不是 process / NDF Control）",
    "- 条款铆钉: [[META-014]] [[BEH-018]] [[CHR-008]] [[META-004]]",
    `- git HEAD: ${head || "(pending snapshot)"}`,
    "",
    "## 下一步",
    "1. Command Agent 组 control-pack / 产品提案 hop（new-proposal）",
    "2. 人工「已确认」后落地；「已审核」后再委派实现",
    "3. MUST NOT 把 Overview 意图写成 process proposal 或直接改 spec/meta/",
  ].join("\n");
}
