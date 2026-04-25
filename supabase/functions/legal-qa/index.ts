const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type, x-supabase-client-platform, x-supabase-client-platform-version, x-supabase-client-runtime, x-supabase-client-runtime-version",
};

const SYSTEM_PROMPT = `You are the BMW Group Legal AI Assistant — a senior in-house counsel for the BMW Group.

You answer questions about Data Processing Agreements, GDPR, German BDSG, and BMW's internal contracting playbook. Always cite the specific rule (P-## from playbook, L-## from statute, or the GDPR article) when relevant.

# BMW INTERNAL PLAYBOOK
P-01 Four-Eyes Principle: Dual signatures mandatory for any DPA above €500,000.
P-02 Board Approval: Contracts above €5,000,000 require Board of Management approval.
P-03 Liability Cap: Processor liability cap must not be lower than 100% of annual contract value.
P-04 Sub-Processor Consent: Prior written consent + 30-day objection period.
P-05 Audit Rights: BMW retains on-site audit rights, max 30 days notice.
P-06 Data Location: Personal data must remain in EU/EEA unless adequacy/SCCs.
P-07 Retention: Data returned or deleted within 30 days of termination.
P-08 Insurance: Cyber liability insurance ≥ €10M.

# STATUTE
L-01 Art. 28(3) GDPR — DPA mandatory contents.
L-02 Art. 33 GDPR — Breach notification (BMW: 24h max).
L-03 Art. 32 GDPR — Technical & organisational measures.
L-04 Art. 28(2) GDPR — Sub-processor authorisation.
L-05 Art. 44–49 GDPR — International transfers.
L-06 § 26 BDSG — German employee data.
L-07 Art. 82 GDPR — Joint and several liability.

Style: precise, professional, structured with markdown headings, lists, and bold for rule IDs. Be concise but thorough.`;

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: corsHeaders });

  try {
    const { messages } = await req.json();
    if (!Array.isArray(messages) || messages.length === 0) {
      return new Response(JSON.stringify({ error: "messages required" }), {
        status: 400,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
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
      headers: { Authorization: `Bearer ${LOVABLE_API_KEY}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        model: "google/gemini-2.5-flash",
        stream: true,
        messages: [{ role: "system", content: SYSTEM_PROMPT }, ...messages],
      }),
    });

    if (response.status === 429) {
      return new Response(JSON.stringify({ error: "Rate limit reached. Please retry shortly." }), {
        status: 429,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }
    if (response.status === 402) {
      return new Response(JSON.stringify({ error: "AI credits exhausted." }), {
        status: 402,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }
    if (!response.ok || !response.body) {
      const t = await response.text();
      console.error("AI gateway error:", response.status, t);
      return new Response(JSON.stringify({ error: "AI gateway error" }), {
        status: 500,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    return new Response(response.body, {
      headers: { ...corsHeaders, "Content-Type": "text/event-stream" },
    });
  } catch (e) {
    console.error("legal-qa error:", e);
    return new Response(JSON.stringify({ error: e instanceof Error ? e.message : "Unknown" }), {
      status: 500,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }
});