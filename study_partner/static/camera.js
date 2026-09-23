// ROI coordinates always refer to the displayed, oriented image.
// One transform serves preview, AI capture and motion sampling.
export function drawCameraRegion(ctx, source, width, height, roi, flipX, flipY) {
  const sx = (flipX ? 1 - roi.x - roi.w : roi.x) * width;
  const sy = (flipY ? 1 - roi.y - roi.h : roi.y) * height;
  ctx.save();
  ctx.translate(flipX ? ctx.canvas.width : 0, flipY ? ctx.canvas.height : 0);
  ctx.scale(flipX ? -1 : 1, flipY ? -1 : 1);
  ctx.drawImage(source, sx, sy, roi.w * width, roi.h * height,
    0, 0, ctx.canvas.width, ctx.canvas.height);
  ctx.restore();
}
