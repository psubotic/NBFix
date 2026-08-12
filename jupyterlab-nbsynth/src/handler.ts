import { URLExt } from '@jupyterlab/coreutils';
import { ServerConnection } from '@jupyterlab/services';

/**
 * Call the NBSynth server extension API.
 *
 * @param endPoint API REST end point for the extension
 * @param init Initial values for the request
 * @returns The response body interpreted as JSON
 */
export async function requestAPI<T>(
  endPoint = '',
  init: RequestInit = {}
): Promise<T> {
  const settings = ServerConnection.makeSettings();
  const requestUrl = URLExt.join(settings.baseUrl, 'nbsynth', 'api', endPoint);

  let response: Response;
  try {
    response = await ServerConnection.makeRequest(requestUrl, init, settings);
  } catch (error) {
    throw new ServerConnection.NetworkError(error as any);
  }

  let data: any = await response.text();

  if (data.length > 0) {
    try {
      data = JSON.parse(data);
    } catch (error) {
      console.log('Not a JSON response body.', response);
    }
  }

  if (!response.ok) {
    throw new ServerConnection.ResponseError(response, data.message || data);
  }

  return data;
}

export interface INBSynthDiagnostic {
  cell_id: number;
  errors: Array<{
    line: number;
    label: string;
    error_type: string;
    message: string;
  }>;
}

export interface INBSynthEventResponse {
  status: 'success' | 'error';
  diagnostics?: INBSynthDiagnostic[];
  message?: string;
}

/**
 * Sends a single NBSynth event to the server extension's event endpoint.
 */
export function postEvent(
  eventName: string,
  notebookId: string,
  params?: Record<string, unknown>
): Promise<INBSynthEventResponse> {
  return requestAPI<INBSynthEventResponse>('event', {
    method: 'POST',
    body: JSON.stringify({
      event: eventName,
      notebook_id: notebookId,
      params: params ?? {}
    })
  });
}
