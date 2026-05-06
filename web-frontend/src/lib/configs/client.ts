import { apiClient, apiGet } from '$lib/api/client.js';

export interface AskCredentialProvider {
  id: string;
  label: string;
  env_key: string;
  configured: boolean;
  fingerprint: string | null;
}

export interface ConfigsResponse {
  ask_credentials: {
    providers: AskCredentialProvider[];
  };
}

function configsPath(vaultName: string) {
  return `/api/v1/vault/${encodeURIComponent(vaultName)}/configs`;
}

function askCredentialPath(vaultName: string, providerId: string) {
  return `${configsPath(vaultName)}/ask/credentials/${encodeURIComponent(providerId)}`;
}

export async function loadConfigs(vaultName: string) {
  return apiGet<ConfigsResponse>(configsPath(vaultName));
}

export async function saveAskCredential(
  vaultName: string,
  providerId: string,
  apiKey: string
): Promise<void> {
  const response = await apiClient(askCredentialPath(vaultName, providerId), {
    method: 'PUT',
    body: JSON.stringify({ api_key: apiKey })
  });
  if (!response.ok) {
    throw new Error(`PUT ask credential → ${response.status}`);
  }
}

export async function deleteAskCredential(vaultName: string, providerId: string): Promise<void> {
  const response = await apiClient(askCredentialPath(vaultName, providerId), {
    method: 'DELETE'
  });
  if (!response.ok) {
    throw new Error(`DELETE ask credential → ${response.status}`);
  }
}
