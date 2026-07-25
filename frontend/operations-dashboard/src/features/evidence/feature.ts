export function isEvidenceBrowserEnabled(): boolean {
  return process.env.EVIDENCE_BROWSER_ENABLED === "true";
}
