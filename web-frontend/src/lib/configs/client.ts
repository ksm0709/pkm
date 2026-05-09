import { apiClient, apiGet } from "$lib/api/client.js";

export interface AskCredentialProvider {
  id: string;
  label: string;
  env_key: string;
  configured: boolean;
  fingerprint: string | null;
}

export interface ConfigSetting {
  key: string;
  section: string;
  internal_key: string;
  description: string;
  value: string;
  default_value: string;
  configured: boolean;
  source: "configured" | "default" | "unset";
  input_type: "text" | "number" | "boolean";
  options: string[];
}

export interface ConfigsResponse {
  settings: ConfigSetting[];
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

function configSettingPath(vaultName: string, key: string) {
  return `${configsPath(vaultName)}/settings/${encodeURIComponent(key)}`;
}

export async function loadConfigs(vaultName: string) {
  return apiGet<ConfigsResponse>(configsPath(vaultName));
}

export async function saveConfigSetting(
  vaultName: string,
  key: string,
  value: string | boolean | number | null,
): Promise<ConfigSetting> {
  const response = await apiClient(configSettingPath(vaultName, key), {
    method: "PATCH",
    body: JSON.stringify({ value }),
  });
  if (!response.ok) {
    throw new Error(`PATCH config setting → ${response.status}`);
  }
  return (await response.json()) as ConfigSetting;
}

export async function saveAskCredential(
  vaultName: string,
  providerId: string,
  apiKey: string,
): Promise<void> {
  const response = await apiClient(askCredentialPath(vaultName, providerId), {
    method: "PUT",
    body: JSON.stringify({ api_key: apiKey }),
  });
  if (!response.ok) {
    throw new Error(`PUT ask credential → ${response.status}`);
  }
}

export async function deleteAskCredential(
  vaultName: string,
  providerId: string,
): Promise<void> {
  const response = await apiClient(askCredentialPath(vaultName, providerId), {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error(`DELETE ask credential → ${response.status}`);
  }
}
