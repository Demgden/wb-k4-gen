# reference_works —— 真实参考作品索引

这些 `.bcm4` 是**已验证能在 kitten4 编辑器打开/运行**的真实作品，用作：
① 积木用法的 ground truth（`query_block.py --use`）；② `bcm4_read.py` 反编译练习。
信封模板在 `../envelopes/`（不在这里）。

## 本目录内（已入 git）

| 文件 | 大小 | 用途 |
|---|---|---|
| `florr合卡.bcm4` | ~240 KB | 过程(procedures_2)定义/调用/参数 shadows+mutation 的紧凑真实实例 |

查询用法：
```bash
python tools/query_block.py --use <积木type>     # 自动扫描本目录全部 .bcm4
python tools/bcm4_read.py reference_works/florr合卡.bcm4
```

## 信封模板（../envelopes/，参与生成）

| 文件 | 大小 | 用途 |
|---|---|---|
| `球体物理.bcm4` | ~3.9 MB | **主信封**。`gen_mount.js` 默认挂载它；2 角色（引擎+计数），挂载时取「引擎」壳 |
| `空白作品.bcm4` | 3.6 KB | 最小信封（边界验证：codemao_value 字符串也合法） |

## Desktop 上的大作品（未入 git，按需拷贝进 reference_works/ 再查）

位于原始开发机的 `Desktop/kitten4作品/`（路径因机器而异，未随仓库分发）：

| 文件 | 大小 | 用途 |
|---|---|---|
| `MagicCatAcademy.bcm4` | ~7.3 MB | 魔法猫学院完整复刻：手势识别、精灵动画、多场景切换、音频切片 |
| `florr-重置版.bcm4` | ~17 MB | 大型作品：复杂数据结构/多列表状态机 |
| `1.bcm4` / `2.bcm4` / `3.bcm4` | 20/3.4/2.5 MB | 早期参照作品 |
| `预瞄.bcm4` | ~2.6 MB | 参照作品 |

## 相关素材目录（Desktop，按需）

- `magic-cat-academy-Google-main/`：Google 原版 sprite（不程序化烘焙）
- `另一个项目/magic-cat-academy/`：干净版参考源码 game.js
- `ts2kitten-main/`、`kitten2scratch-master/`：格式转换参考实现
