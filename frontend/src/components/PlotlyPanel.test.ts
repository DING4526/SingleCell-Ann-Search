// @vitest-environment jsdom
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { reactive } from "vue";
import PlotlyPanel from "@/components/PlotlyPanel.vue";

const plotly = vi.hoisted(() => ({
  react: vi.fn(() => Promise.resolve()),
  restyle: vi.fn(() => Promise.resolve()),
  purge: vi.fn(),
}));

vi.mock("@/services/plotly-runtime", () => ({ default: plotly }));

const payload = {
  data: [{
    marker: { opacity: 0.5, color: ["#155e75", "#7c3aed"] },
    customdata: [[1, "T cell"], [2, "hepatocyte"]],
    x: [0, 1],
    y: [0, 1],
  }],
  layout: { title: "UMAP" },
  metadata: {
    legend: {
      target_trace_index: 0,
      default_dimension: "cell_type",
      dimensions: {
        cell_type: {
          label: "细胞类型",
          customdata_index: 1,
          items: [
            { key: "T cell", label: "T cell", color: "#155e75", count: 1 },
            { key: "hepatocyte", label: "hepatocyte", color: "#7c3aed", count: 1 },
          ],
        },
      },
    },
  },
};

const global = {
  stubs: {
    "a-button": { template: "<button><slot /></button>" },
    "a-empty": { template: "<div><slot />暂无可视化结果</div>" },
    "a-popover": { template: "<div><slot /><slot name='content' /></div>" },
    "a-segmented": { template: "<div />" },
  },
};

function lastRestyleUpdate() {
  const calls = plotly.restyle.mock.calls as unknown as Array<[
    unknown,
    Record<string, number[][]>,
  ]>;
  return calls[calls.length - 1][1];
}

describe("PlotlyPanel", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("可以渲染 Vue 响应式包装的 API 图表数据", async () => {
    const reactivePayload = reactive(JSON.parse(JSON.stringify(payload)));
    mount(PlotlyPanel, { props: { payload: reactivePayload }, global });
    await flushPromises();
    expect(plotly.react).toHaveBeenCalledTimes(1);
  });

  it("单击图例会修改真实散点透明度", async () => {
    const wrapper = mount(PlotlyPanel, { props: { payload }, global });
    await flushPromises();

    const items = wrapper.findAll(".legend-item");
    expect(items).toHaveLength(2);
    await items[0].trigger("click");
    await vi.advanceTimersByTimeAsync(230);
    await flushPromises();

    const update = lastRestyleUpdate();
    expect(update["marker.opacity"][0]).toEqual([0.035, 0.5]);
  });

  it("双击图例只保留目标分类并可在空载荷时清图", async () => {
    const wrapper = mount(PlotlyPanel, { props: { payload }, global });
    await flushPromises();

    await wrapper.findAll(".legend-item")[1].trigger("dblclick");
    await flushPromises();
    const update = lastRestyleUpdate();
    expect(update["marker.opacity"][0]).toEqual([0.035, 0.5]);

    await wrapper.setProps({ payload: null });
    await flushPromises();
    expect(plotly.purge).toHaveBeenCalled();
  });
});
