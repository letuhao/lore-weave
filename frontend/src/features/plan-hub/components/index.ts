// Plan Hub v2 (24 H2.4 + H3/H6) — canvas + node views + drawer + navigator rail public surface.
export { PlanCanvas } from './PlanCanvas';
export { ChapterNode } from './ChapterNode';
export { SceneNode } from './SceneNode';
export { ArcRollupNode } from './ArcRollupNode';
export { LaneBandNode, buildLaneNodes, LANE_NODE_PREFIX } from './LaneBandLayer';
export { PlanDrawer } from './PlanDrawer';
export { PlanNavigatorRail } from './PlanNavigatorRail';
export { PlanEmptyState } from './PlanEmptyState';
export { UnplannedTray } from './UnplannedTray';
export { NodeBadges } from './NodeBadges';
export { PacingSparkline } from './PacingSparkline';
export type { PlanNodeData, LaneBandData, NodeBadge } from './nodePresentation';
