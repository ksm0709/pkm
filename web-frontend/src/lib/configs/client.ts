import { apiClient, apiGet } from "$lib/api/client.js";

export interface ConfigSetting {
  key: string;
  section: string;
  internal_key: string;
  description: string;
  value: string;
  default_value: string;
  configured: boolean;
  source: "configured" | "default" | "unset";
  input_type: "text" | "number" | "boolean" | "select";
  options: string[];
}

export interface ConfigsResponse {
  settings: ConfigSetting[];
}

function configsPath(vaultName: string) {
  return `/api/v1/vault/${encodeURIComponent(vaultName)}/configs`;
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
