import { describe, expect, it } from "vitest";
import {
  canDeleteResource,
  deletionConfirmationDescription,
  readNonNegativeRouteNumber,
  readPositiveRouteNumber,
} from "@/utils/resource-actions";

describe("资源操作与路由参数", () => {
  it("根据权限和结构化阻断信息控制永久删除操作", () => {
    expect(canDeleteResource({ can_delete: true }, true)).toBe(true);
    expect(canDeleteResource({ can_delete: true }, false)).toBe(false);
    const blocked = { can_delete: false, delete_blockers: [{ type: "task", label: "仍有任务运行中" }] };
    expect(canDeleteResource(blocked, true)).toBe(false);
    expect(deletionConfirmationDescription(blocked, "永久删除关联文件")).toBe("当前无法删除：仍有任务运行中");
    expect(deletionConfirmationDescription({ can_delete: true }, "永久删除关联文件")).toBe("永久删除关联文件");
  });

  it("只接受有效的 index_id、数据集和细胞编号查询参数", () => {
    expect(readPositiveRouteNumber("17")).toBe(17);
    expect(readPositiveRouteNumber(["23", "24"])).toBe(23);
    expect(readPositiveRouteNumber("0")).toBeUndefined();
    expect(readPositiveRouteNumber("index-2")).toBeUndefined();
    expect(readNonNegativeRouteNumber("0")).toBe(0);
    expect(readNonNegativeRouteNumber("-1")).toBeUndefined();
  });
});
