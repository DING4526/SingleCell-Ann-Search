import type { DeleteBlocker } from "@/types";

type ResourceActionState = {
  can_delete?: boolean;
  delete_blockers?: DeleteBlocker[];
};

export function canDeleteResource(resource: ResourceActionState, hasPermission = true) {
  return hasPermission && resource.can_delete !== false && !(resource.delete_blockers?.length);
}

export function deleteBlockerSummary(resource: ResourceActionState, fallback = "当前资源暂时不能删除") {
  return resource.delete_blockers?.map((item) => item.label).filter(Boolean).join("；") || fallback;
}

export function deletionConfirmationDescription(resource: ResourceActionState, impact: string) {
  return resource.delete_blockers?.length
    ? `当前无法删除：${deleteBlockerSummary(resource)}`
    : impact;
}

function firstQueryValue(value: unknown) {
  return Array.isArray(value) ? value[0] : value;
}

export function readPositiveRouteNumber(value: unknown) {
  const parsed = Number(firstQueryValue(value));
  return Number.isInteger(parsed) && parsed > 0 ? parsed : undefined;
}

export function readNonNegativeRouteNumber(value: unknown) {
  const parsed = Number(firstQueryValue(value));
  return Number.isInteger(parsed) && parsed >= 0 ? parsed : undefined;
}
