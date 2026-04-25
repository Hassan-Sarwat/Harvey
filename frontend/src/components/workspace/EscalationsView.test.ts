import { describe, expect, it } from "vitest";
import type { TriggerAnnotation } from "@/api/client";
import { buildAnnotationMarkerMap, buildTextSegments, orderAnnotations } from "./EscalationsView";

describe("EscalationsView document helpers", () => {
  it("keeps contract text intact while prioritizing higher-severity overlapping highlights", () => {
    const contractText = "Clause A is ambiguous and illegal.";
    const illegalStart = contractText.indexOf("illegal");
    const illegalEnd = illegalStart + "illegal".length;

    const ambiguous = annotation({
      id: "playbook_checker:ambiguous",
      severity: "low",
      start: 0,
      end: contractText.length,
      title: "Ambiguous wording",
    });
    const illegal = annotation({
      id: "legal_checker:illegal",
      severity: "blocker",
      start: illegalStart,
      end: illegalEnd,
      title: "Potentially illegal wording",
    });

    const segments = buildTextSegments(contractText, [ambiguous, illegal]);

    expect(segments.map((segment) => segment.text).join("")).toBe(contractText);
    expect(segments.find((segment) => segment.text === "illegal")?.annotation?.id).toBe(illegal.id);
    expect(segments.find((segment) => segment.text === "illegal")?.showMarker).toBe(true);
    expect(segments[0].annotation?.id).toBe(ambiguous.id);
    expect(segments[0].showMarker).toBe(true);
  });

  it("orders annotation markers by document position and severity", () => {
    const laterMedium = annotation({ id: "playbook_checker:medium", severity: "medium", start: 25, end: 30 });
    const sameStartLow = annotation({ id: "contract_understanding:low", severity: "low", start: 5, end: 14 });
    const sameStartHigh = annotation({ id: "legal_checker:high", severity: "high", start: 5, end: 10 });

    const ordered = orderAnnotations([laterMedium, sameStartLow, sameStartHigh]);
    const markers = buildAnnotationMarkerMap([laterMedium, sameStartLow, sameStartHigh]);

    expect(ordered.map((item) => item.id)).toEqual([
      "legal_checker:high",
      "contract_understanding:low",
      "playbook_checker:medium",
    ]);
    expect(markers.get("legal_checker:high")).toBe(1);
    expect(markers.get("contract_understanding:low")).toBe(2);
    expect(markers.get("playbook_checker:medium")).toBe(3);
  });
});

function annotation(overrides: Partial<TriggerAnnotation>): TriggerAnnotation {
  return {
    id: "agent:finding",
    agent_name: "agent",
    finding_id: "finding",
    title: "Finding",
    description: "Description",
    severity: "low",
    requires_escalation: false,
    start: 0,
    end: 1,
    text: "text",
    ruling: null,
    suggestions: [],
    ...overrides,
  };
}
