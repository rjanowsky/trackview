"""[Phase 4 / 4.1] The map figure's pure geometry helper -- `fit_aspect`.

The heavy `render` orchestrator is the `@pytest.mark.slow` figure path
(test_render_smoke); but `fit_aspect` is pure math over a bbox -- it grows
(west, south, east, north) so the map's bounding box matches the figure's
width:height aspect (a square FIGURE_IN keeps the image un-letterboxed) -- so it
gets a fast, offline unit test.  The figure render itself is not drawn here.
"""
from trackview.mapfig import fit_aspect


class TestFitAspect:
    def test_a_square_bbox_at_square_aspect_is_untouched(self):
          # bw == bh and aspect_wh == 1.0: neither pad branch fires
        assert fit_aspect((0.0, 0.0, 1.0, 1.0), 1.0) == (0.0, 0.0, 1.0, 1.0)

    def test_a_narrow_bbox_is_padded_east_and_west(self):
          # bw < bh (a tall box) under a square aspect: widen east/west, keep s/n
        out = fit_aspect((0.0, 0.0, 1.0, 2.0), 1.0)
        assert out == (-0.5, 0.0, 1.5, 2.0)
        assert out[1] == 0.0 and out[3] == 2.0        # south / north unchanged

    def test_a_wide_bbox_is_padded_north_and_south(self):
          # bw > bh (a wide box): grow north/south, keep w/e
        out = fit_aspect((0.0, 0.0, 2.0, 1.0), 1.0)
        assert out == (0.0, -0.5, 2.0, 1.5)
        assert out[0] == 0.0 and out[2] == 2.0        # west / east unchanged

    def test_a_non_square_figure_aspect_pads_to_fill(self):
          # aspect_wh = 2.0 (a landscape figure) on a square bbox pads east/west
        out = fit_aspect((0.0, 0.0, 1.0, 1.0), 2.0)
        assert out == (-0.5, 0.0, 1.5, 1.0)

    def test_padding_is_centred_on_a_non_origin_bbox(self):
          # the pad is symmetric about the box centre, off the origin
        out = fit_aspect((10.0, 20.0, 12.0, 24.0), 1.0)
        assert out == (9.0, 20.0, 13.0, 24.0)
        assert (out[0] + out[2]) / 2 == 11.0          # west/east centred on x=11
        assert (out[1] + out[3]) / 2 == 22.0          # s/n unchanged, centred on y=22

    def test_the_grown_box_matches_the_figure_aspect(self):
          # after growth the bbox's width:height equals the requested aspect
        out = fit_aspect((0.0, 0.0, 1.0, 1.0), 2.0)
        w, s, e, n = out
        assert (e - w) / (n - s) == 2.0
