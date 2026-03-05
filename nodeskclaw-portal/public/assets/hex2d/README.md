# Hex 2D 素材规格

放置 2D 工作区地板纹理和家具精灵的目录。

## 目录结构

```
hex2d/
  floors/
    carpet-warm.svg    暖色地毯
    carpet-cool.svg    冷色地毯
    carpet-marble.svg  大理石
  furniture/
    office-chair.svg   办公椅
    office-desk.svg    办公桌
    desk-lamp.svg      台灯
    stool.svg          凳子
```

当前使用 SVG 占位素材（Figma MCP 额度受限）。替换为 Figma 导出的 PNG 后需同步更新 `src/config/decorationAssets.ts` 中的 URL。

## Hex Cell 尺寸

当前参数：

| 参数 | 值 |
|---|---|
| HEX_SIZE | 1.2 |
| SCALE | 60 |
| HEX_RADIUS | HEX_SIZE * SCALE * 0.85 = 61.2 |
| Y_SCALE | 0.3 ~ 1.0（通过装修面板的"视角比例"滑块实时调节） |

计算公式：

```
cell_width  = sqrt(3) * HEX_RADIUS = 106 px
cell_height = 2 * HEX_RADIUS * Y_SCALE
```

| Y_SCALE | cell_width | cell_height |
|---|---|---|
| 1.0 | 106 px | 122 px |
| 0.7 | 106 px | 86 px |
| 0.5 | 106 px | 61 px |

## 素材要求

- 格式：PNG 或 SVG
- 背景：透明
- 尺寸：不小于 cell bounding box（上表），建议 2x 以获得 Retina 清晰度
- 地板纹理：用 `preserveAspectRatio="xMidYMid slice"` 裁切填满 hex cell
- 家具精灵：用 `preserveAspectRatio="xMidYMid meet"` 保持原始比例居中

## 素材注册

所有素材必须在 `nodeskclaw-portal/src/config/decorationAssets.ts` 中注册后才能在装修面板中使用。
