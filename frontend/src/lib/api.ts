/**
 * Axios instance for ConstructAI – communicates with the FastAPI backend.
 *
 * Usage:
 *   import api from '@/lib/api';
 *   const data = await api.get('/projects');
 *
 * Token lifecycle:
 *   - On successful FastAPI login, store the returned JWT with `setApiToken()`.
 *   - The request interceptor picks it up automatically on every request.
 *   - On 401 the response interceptor clears the token and redirects to /login.
 */

import axios, {
  type AxiosInstance,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
  type AxiosError,
} from 'axios';

// ── Constants ──────────────────────────────────────────────────────────────────

/** Key used to persist the FastAPI JWT in localStorage. */
const TOKEN_KEY = 'constructai_api_token';

/** Base URL for all API requests.  Override via NEXT_PUBLIC_API_URL in .env */
const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8000/api';

// ── TypeScript interfaces ──────────────────────────────────────────────────────

/** Shape of the JSON body returned by FastAPI on validation / HTTP errors. */
export interface ApiErrorBody {
  detail: string | { msg: string; type: string }[];
}

/** Wrapper that carries both the Axios error and the parsed error body. */
export interface ApiError extends AxiosError<ApiErrorBody> {
  /** Human-readable message extracted from the FastAPI response body. */
  friendlyMessage: string;
}

// ── Token helpers ──────────────────────────────────────────────────────────────

/** Returns true when running in a browser (guards against SSR). */
const isBrowser = (): boolean => typeof window !== 'undefined';

/**
 * Read the JWT from localStorage.
 * Returns `null` when called server-side or when no token is stored.
 */
export const getApiToken = (): string | null => {
  if (!isBrowser()) return null;
  return localStorage.getItem(TOKEN_KEY);
};

/**
 * Persist a JWT returned by the FastAPI login endpoint.
 * Call this after a successful `/auth/login` response.
 */
export const setApiToken = (token: string): void => {
  if (!isBrowser()) return;
  localStorage.setItem(TOKEN_KEY, token);
};

/**
 * Remove the stored JWT.
 * Called automatically on 401; can also be called explicitly on logout.
 */
export const clearApiToken = (): void => {
  if (!isBrowser()) return;
  localStorage.removeItem(TOKEN_KEY);
};

// ── Axios instance ─────────────────────────────────────────────────────────────

const api: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 15_000,
  headers: {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  },
});

// ── Request interceptor ────────────────────────────────────────────────────────

/**
 * Attach the Bearer token to every outgoing request when one is available.
 */
api.interceptors.request.use(
  (config: InternalAxiosRequestConfig): InternalAxiosRequestConfig => {
    const token = getApiToken();
    if (token) {
      config.headers.set('Authorization', `Bearer ${token}`);
    }
    return config;
  },
  (error: unknown) => Promise.reject(error),
);

// ── Response interceptor ───────────────────────────────────────────────────────

/**
 * Pass successful responses through unchanged.
 * On error:
 *  - 401 Unauthorized → clear token + redirect to /login.
 *  - Other status codes → enrich the error with a `friendlyMessage` string
 *    extracted from the FastAPI `detail` field, then re-throw.
 */
api.interceptors.response.use(
  (response: AxiosResponse): AxiosResponse => response,

  (error: AxiosError<ApiErrorBody>): Promise<never> => {
    const status = error.response?.status;

    if (status === 401) {
      clearApiToken();

      // Guard: redirect only runs in the browser (not during SSR/API routes).
      if (isBrowser()) {
        window.location.href = '/login';
      }

      return Promise.reject(buildApiError(error, 'Session expired. Please log in again.'));
    }

    return Promise.reject(buildApiError(error));
  },
);

// ── Error builder ──────────────────────────────────────────────────────────────

/**
 * Enrich an AxiosError with a human-readable `friendlyMessage` by parsing the
 * FastAPI `detail` field (which can be a plain string or a list of validation
 * error objects).
 */
function buildApiError(
  error: AxiosError<ApiErrorBody>,
  overrideMessage?: string,
): ApiError {
  let friendlyMessage =
    overrideMessage ?? 'An unexpected error occurred. Please try again.';

  if (!overrideMessage && error.response?.data?.detail) {
    const detail = error.response.data.detail;

    if (typeof detail === 'string') {
      friendlyMessage = detail;
    } else if (Array.isArray(detail) && detail.length > 0) {
      // FastAPI validation errors: join all messages into one string.
      friendlyMessage = detail.map((d) => d.msg).join('; ');
    }
  }

  return Object.assign(error, { friendlyMessage }) as ApiError;
}

export default api;
