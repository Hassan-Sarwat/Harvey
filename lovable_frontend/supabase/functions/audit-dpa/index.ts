const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type, x-supabase-client-platform, x-supabase-client-platform-version, x-supabase-client-runtime, x-supabase-client-runtime-version",
};

const SYSTEM_PROMPT = `You are the BMW Group Legal AI Auditor — a senior in-house counsel reviewing third-party Data Processing Agreements (DPAs) for the BMW Group.

You audit contracts against TWO knowledge bases:

# 1. BMW INTERNAL PLAYBOOK (Corporate Standards)

P-01 — FOUR-EYES PRINCIPLE: Every DPA above €500,000 contract value MUST carry two authorised BMW signatures (dual signatures mandatory). Single-signature clauses are non-compliant.
P-02 — BOARD APPROVAL THRESHOLD: Any contract with annual value exceeding €5,000,000 requires Board of Management approval. Mark such contracts as escalation_required = true.
P-03 — LIABILITY CAP: Processor liability cap must NOT be lower than 100% of annual contract value. Caps at "12 months fees" or lower for data breaches are non-compliant.
P-04 — SUB-PROCESSOR CONSENT: BMW requires PRIOR WRITTEN consent for new sub-processors with a minimum 30-day objection period. "General authorisation" or "notification only" clauses fail.
P-05 — AUDIT RIGHTS: BMW must retain on-site audit rights with maximum 30 days notice. Audit-by-third-party-only clauses or excessive notice (>60 days) are non-compliant.
P-06 — DATA LOCATION: Personal data must be processed within the EU/EEA unless adequacy decision or BMW-approved SCCs are in place. Unrestricted "global processing" fails.
P-07 — RETENTION: Data must be returned or deleted within 30 days of contract termination. Longer retention requires explicit BMW Legal sign-off.
P-08 — INSURANCE: Processor must maintain cyber liability insurance ≥ €10M.

# 2. STATUTORY LAW (GDPR + German BDSG)

L-01 — Art. 28(3) GDPR: DPA must specify subject-matter, duration, nature/purpose, type of personal data, categories of data subjects, and obligations/rights of controller.
L-02 — Art. 33 GDPR: Processor must notify controller of personal data breach WITHOUT UNDUE DELAY — interpreted as 24 hours maximum for the BMW Group. Anything beyond 72 hours is a hard fail.
L-03 — Art. 32 GDPR: Technical and organisational measures (TOMs) must be specified — encryption at rest/in transit, pseudonymisation, access controls, regular testing.
L-04 — Art. 28(2) GDPR: No engagement of sub-processor without prior specific or general written authorisation of controller.
L-05 — Art. 44–49 GDPR: International transfers require appropriate safeguards (SCCs, adequacy, BCRs).
L-06 — § 26 BDSG: Special rules for employee data processing.
L-07 — Art. 82 GDPR: Joint and several liability for damages — clauses limiting controller's claim against processor are void.

# YOUR TASK

Audit the provided contract text. Identify EVERY violation of the rules above. Be thorough, specific, and cite the exact rule ID (P-## or L-##).

Severity rules:
- HIGH: violates a hard statutory rule (L-##) OR a financial/escalation playbook rule (P-01, P-02, P-03)
- MEDIUM: violates an operational playbook rule (P-04 through P-08)

Status rules:
- "Rejected" if any HIGH severity violation exists
- "Escalated" if escalation_required is true OR only MEDIUM violations exist
- "Approved" only if zero violations

Set escalation_required = true if:
- Contract value > €5,000,000 (P-02), OR
- Any HIGH severity statutory violation (L-##)

For each violation, provide a CONCRETE redline suggestion — actual replacement text the lawyer can paste into the contract.

Return ONLY valid JSON matching the provided schema. No prose, no markdown.`;

const auditSchema = {
  type: "object",
  properties: {
    contract_summary: { type: "string", description: "1-2 sentence description of the contract type, parties, and scope." },
    contract_value_eur: { type: "number", description: "Estimated annual contract value in EUR if mentioned, else 0." },
    status: { type: "string", enum: ["Approved", "Escalated", "Rejected"] },
    escalation_required: { type: "boolean" },
    violations: {
      type: "array",
      items: {
        type: "object",
        properties: {
          severity: { type: "string", enum: ["High", "Medium"] },
          clause: { type: "string", description: "Exact text quoted from the contract." },
          issue: { type: "string", description: "Why this fails — clear, 1-2 sentences." },
          reference: { type: "string", description: "Rule ID (e.g. P-01, L-02) and short rule name." },
          suggestion: { type: "string", description: "Concrete redline replacement text." },
        },
        required: ["severity", "clause", "issue", "reference", "suggestion"],
        additionalProperties: false,
      },
    },
  },
  required: ["contract_summary", "status", "escalation_required", "violations"],
  additionalProperties: false,
};

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: corsHeaders });

  try {
    const { contractText } = await req.json();
    if (!contractText || typeof contractText !== "string" || contractText.trim().length < 50) {
      return new Response(
        JSON.stringify({ error: "contractText is required and must contain meaningful contract content." }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    const LOVABLE_API_KEY = Deno.env.get("LOVABLE_API_KEY");
    if (!LOVABLE_API_KEY) {
      return new Response(JSON.stringify({ error: "AI gateway not configured." }), {
        status: 500,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const response = await fetch("https://ai.gateway.lovable.dev/v1/chat/completions", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${LOVABLE_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: "google/gemini-2.5-pro",
        messages: [
          { role: "system", content: SYSTEM_PROMPT },
          { role: "user", content: `Audit the following DPA. Return only the structured tool call.\n\n---CONTRACT START---\n${contractText.slice(0, 60000)}\n---CONTRACT END---` },
        ],
        tools: [
          {
            type: "function",
            function: {
              name: "submit_audit",
              description: "Submit the structured DPA audit result.",
              parameters: auditSchema,
            },
          },
        ],
        tool_choice: { type: "function", function: { name: "submit_audit" } },
      }),
    });

    if (response.status === 429) {
      return new Response(JSON.stringify({ error: "Rate limit reached. Please retry shortly." }), {
        status: 429,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }
    if (response.status === 402) {
      return new Response(JSON.stringify({ error: "AI credits exhausted. Add funds in workspace settings." }), {
        status: 402,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }
    if (!response.ok) {
      const text = await response.text();
      console.error("AI gateway error:", response.status, text);
      return new Response(JSON.stringify({ error: "AI gateway error." }), {
        status: 500,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const data = await response.json();
    const toolCall = data.choices?.[0]?.message?.tool_calls?.[0];
    if (!toolCall?.function?.arguments) {
      console.error("No tool call in response:", JSON.stringify(data));
      return new Response(JSON.stringify({ error: "AI did not return structured audit." }), {
        status: 500,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const audit = JSON.parse(toolCall.function.arguments);
    return new Response(JSON.stringify(audit), {
      status: 200,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  } catch (e) {
    console.error("audit-dpa error:", e);
    return new Response(
      JSON.stringify({ error: e instanceof Error ? e.message : "Unknown error" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } },
    );
  }
});