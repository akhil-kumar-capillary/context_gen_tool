const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

interface FetchOptions extends RequestInit {
  token?: string;
  /** Override the default 30s request timeout (ms). Use for slow endpoints like context upload. */
  timeoutMs?: number;
}

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(
    path: string,
    options: FetchOptions = {}
  ): Promise<T> {
    const { token, timeoutMs, ...fetchOptions } = options;

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(options.headers as Record<string, string>),
    };

    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs ?? 30_000);
    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}${path}`, {
        ...fetchOptions,
        headers,
        signal: controller.signal,
      });
    } catch (err) {
      clearTimeout(timeout);
      if (err instanceof DOMException && err.name === "AbortError") {
        throw new ApiError(0, "Request timed out");
      }
      throw new ApiError(0, "Network error");
    }
    clearTimeout(timeout);

    if (!response.ok) {
      // Auto-logout on auth failure — token expired or invalid
      if (response.status === 401) {
        try {
          const { useAuthStore } = await import("@/stores/auth-store");
          useAuthStore.getState().logout();
        } catch {
          // Ignore import/logout errors — redirect handles recovery
        }
        if (typeof window !== "undefined") {
          window.location.href = "/login";
        }
        throw new ApiError(401, "Session expired");
      }

      const error = await response.json().catch(() => ({
        detail: response.statusText,
      }));
      throw new ApiError(response.status, error.detail || "Request failed");
    }

    return response.json();
  }

  async get<T>(path: string, options?: FetchOptions): Promise<T> {
    return this.request<T>(path, { ...options, method: "GET" });
  }

  async post<T>(
    path: string,
    body?: unknown,
    options?: FetchOptions
  ): Promise<T> {
    return this.request<T>(path, {
      ...options,
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  async put<T>(
    path: string,
    body?: unknown,
    options?: FetchOptions
  ): Promise<T> {
    return this.request<T>(path, {
      ...options,
      method: "PUT",
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  async delete<T>(path: string, options?: FetchOptions): Promise<T> {
    return this.request<T>(path, { ...options, method: "DELETE" });
  }

  /**
   * Multipart POST for file uploads. Does NOT set Content-Type — the browser
   * adds its own with the correct multipart boundary.
   *
   * `onProgress` receives values in the range [0, 1]. Progress is driven by
   * XMLHttpRequest because fetch() has no native upload-progress event.
   */
  async postFormData<T>(
    path: string,
    formData: FormData,
    options: { token?: string; onProgress?: (p: number) => void; timeoutMs?: number } = {}
  ): Promise<T> {
    const { token, onProgress, timeoutMs = 600_000 } = options;
    const url = `${this.baseUrl}${path}`;

    return new Promise<T>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", url, true);
      xhr.timeout = timeoutMs;
      if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);

      if (onProgress) {
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) onProgress(e.loaded / e.total);
        };
      }

      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            resolve(JSON.parse(xhr.responseText) as T);
          } catch {
            reject(new ApiError(xhr.status, "Invalid JSON response"));
          }
          return;
        }
        if (xhr.status === 401) {
          import("@/stores/auth-store")
            .then(({ useAuthStore }) => useAuthStore.getState().logout())
            .catch(() => {});
          if (typeof window !== "undefined") window.location.href = "/login";
          reject(new ApiError(401, "Session expired"));
          return;
        }
        let detail = xhr.statusText;
        try {
          const parsed = JSON.parse(xhr.responseText);
          detail = parsed.detail || detail;
        } catch {
          // Use statusText as-is
        }
        reject(new ApiError(xhr.status, detail || "Upload failed"));
      };

      xhr.onerror = () => reject(new ApiError(0, "Network error"));
      xhr.ontimeout = () => reject(new ApiError(0, "Upload timed out"));

      xhr.send(formData);
    });
  }
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

export const apiClient = new ApiClient(API_BASE);
