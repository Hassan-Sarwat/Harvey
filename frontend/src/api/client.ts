type RequestOptions = {
  method?: "GET" | "POST";
  body?: unknown;
};

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await fetch(path, {
    method: options.method ?? "GET",
    headers: { "Content-Type": "application/json" },
    body: options.body ? JSON.stringify(options.body) : undefined
  });

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export function reviewContract(contractText: string, contractType: string) {
  return request<Record<string, unknown>>("/contracts/demo-contract-1/review", {
    method: "POST",
    body: { contract_text: contractText, contract_type: contractType }
  });
}

export function askLegalQuestion(question: string, useCase: string, contractType: string) {
  return request<Record<string, unknown>>("/legal-qa", {
    method: "POST",
    body: { question, use_case: useCase, contract_type: contractType }
  });
}

export function listEscalations() {
  return request<Record<string, unknown>>("/escalations");
}

export function getDashboardMetrics() {
  return request<Record<string, unknown>>("/dashboard/metrics");
}
