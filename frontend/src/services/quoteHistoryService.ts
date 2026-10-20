import { API_BASE_URL } from "../config/api";

export interface Quote {
  id: string;
  cliente: string;
  codigo: string;
  producto: string;
  grupo: string;
  cantidad: number;
  precio_unitario: number;
  descuento: number;
  total: number;
  fecha: string;
}

export interface QuoteFilters {
  cliente?: string;
  desde?: string;
  hasta?: string;
  producto?: string;
}

export interface HistoryResponse {
  status: string;
  message: string;
  data: Quote[];
}

async function getHistory(filters?: QuoteFilters, signal?: AbortSignal): Promise<Quote[]> {
  const params = new URLSearchParams();
  if (filters?.cliente) params.append("cliente", filters.cliente);
  if (filters?.desde) params.append("desde", filters.desde);
  if (filters?.hasta) params.append("hasta", filters.hasta);
  if (filters?.producto) params.append("producto", filters.producto);

  const queryString = params.toString();
  const url = `${API_BASE_URL}/api/quotes/history?${queryString}`;
  
  let response: Response;
  try {
    response = await fetch(url, { signal });
  } catch (err: unknown) {
    // Re-throw AbortError so the caller can handle it
    if (err instanceof DOMException && err.name === "AbortError") {
      throw err;
    }
    throw new Error(
      `Network error fetching history: ${err instanceof Error ? err.message : "Unknown error"}`
    );
  }

  if (!response.ok) {
    const errorBody = await response.json().catch(() => null);
    throw new Error(
      errorBody?.detail || `HTTP ${response.status}: ${response.statusText}`
    );
  }

  let result: HistoryResponse;
  try {
    result = await response.json();
  } catch {
    throw new Error("Invalid JSON response from server");
  }

  return Array.isArray(result.data) ? result.data : [];
}

export const quoteHistoryService = { getHistory };
export default quoteHistoryService;
