namespace SRW.Desktop.Hosting;

/// <summary>
/// Initial window placement, computed in WPF device-independent pixels (DIP).
///
/// The work area reported by <c>SystemParameters.WorkArea</c> is already in DIP,
/// so nothing here converts to or assumes physical pixels. This lives outside
/// MainWindow only so the DPI/resolution matrix can be asserted on CI without a
/// GUI session; it holds no window or WPF reference.
/// </summary>
public static class WindowPlacement
{
    /// <summary>
    /// Conservative initial breathing room around the work area. It is a starting
    /// margin, not a proof that every mixed-DPI or multi-monitor layout is correct.
    /// </summary>
    public const double WorkAreaMargin = 0.92;

    public readonly record struct Result(
        double Width,
        double Height,
        double MinWidth,
        double MinHeight,
        double Left,
        double Top,
        bool Changed);

    /// <summary>
    /// Clamp an initial size into the work area and centre it there.
    /// MinWidth/MinHeight are lowered only when they cannot fit, otherwise a small
    /// screen would keep the window larger than the desktop.
    /// </summary>
    public static Result Fit(
        double width,
        double height,
        double minWidth,
        double minHeight,
        double workLeft,
        double workTop,
        double workWidth,
        double workHeight)
    {
        if (workWidth <= 0 || workHeight <= 0 || double.IsNaN(workWidth) || double.IsNaN(workHeight))
        {
            return new Result(width, height, minWidth, minHeight, 0, 0, false);
        }

        var maxWidth = workWidth * WorkAreaMargin;
        var maxHeight = workHeight * WorkAreaMargin;
        var effectiveMinWidth = Math.Min(minWidth, maxWidth);
        var effectiveMinHeight = Math.Min(minHeight, maxHeight);
        var fittedWidth = Math.Max(Math.Min(width, maxWidth), effectiveMinWidth);
        var fittedHeight = Math.Max(Math.Min(height, maxHeight), effectiveMinHeight);

        var changed = fittedWidth < width
                      || fittedHeight < height
                      || effectiveMinWidth < minWidth
                      || effectiveMinHeight < minHeight;

        var left = workLeft + ((workWidth - fittedWidth) / 2d);
        var top = workTop + ((workHeight - fittedHeight) / 2d);
        return new Result(fittedWidth, fittedHeight, effectiveMinWidth, effectiveMinHeight, left, top, changed);
    }
}
