/**
 * Base HTTP client for a coach API. Errors carry the server's i18n
 * message_key (error envelope `{"error": {"code", "message_key"}}`) so
 * screens can render them localized.
 */
import type { SupabaseClient } from '@supabase/supabase-js';

export class ApiError extends Error {
  constructor(
    public readonly code: string,
    public readonly messageKey: string
  ) {
    super(code);
  }
}

export function createApiClient(supabase: SupabaseClient, apiUrl: string) {
  async function authHeader(): Promise<Record<string, string>> {
    const { data } = await supabase.auth.getSession();
    const token = data.session?.access_token;
    if (!token) throw new ApiError('unauthorized', 'errors.unauthorized');
    return { Authorization: `Bearer ${token}` };
  }

  async function send(method: 'GET' | 'POST' | 'DELETE', path: string, body?: object): Promise<Response> {
    try {
      return await fetch(`${apiUrl}${path}`, {
        method,
        headers: { 'Content-Type': 'application/json', ...(await authHeader()) },
        body: body ? JSON.stringify(body) : undefined,
      });
    } catch (error) {
      if (error instanceof ApiError) throw error;
      throw new ApiError('network', 'errors.network');
    }
  }

  async function throwIfError(response: Response): Promise<void> {
    if (response.ok) return;
    let code = 'internal';
    let messageKey = 'errors.internal';
    try {
      const parsed = await response.json();
      code = parsed?.error?.code ?? code;
      messageKey = parsed?.error?.message_key ?? messageKey;
    } catch {
      // non-JSON error body: keep defaults
    }
    throw new ApiError(code, messageKey);
  }

  async function request<T>(method: 'GET' | 'POST', path: string, body?: object): Promise<T> {
    const response = await send(method, path, body);
    await throwIfError(response);
    return (await response.json()) as T;
  }

  /** For endpoints that respond 204 No Content (push-tokens, 004) --
   * `request<T>` always calls `.json()` on success, which would throw on
   * an empty body. */
  async function requestVoid(method: 'POST' | 'DELETE', path: string, body: object): Promise<void> {
    const response = await send(method, path, body);
    await throwIfError(response);
  }

  return { request, requestVoid };
}
