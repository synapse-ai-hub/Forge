/**
 * Single source of the backend base URL.
 *
 * `VITE_MODE` picks which variable is read: `prod` uses `VITE_URL_PROD`,
 * any other value uses `VITE_URL_DEV`. Both live in the root `.env`.
 * An empty value means same origin (e.g. the Docker image, which serves the
 * frontend from the backend).
 */
export const IS_PROD = import.meta.env.VITE_MODE === "prod";

export const API_BASE_URL: string =
  (IS_PROD ? import.meta.env.VITE_URL_PROD : import.meta.env.VITE_URL_DEV) ?? "";

/**
 * Standard envelope of the backend JSON responses.
 */
export interface ApiResponse<T = unknown> {
  status: string;
  message?: string;
  data?: T;
}
