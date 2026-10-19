from ecu_studio.core.plot_axes import sampled_axis_positions

def test_physical_axis_keeps_actual_nonuniform_spacing():
    positions,truth=sampled_axis_positions([1000,1500,3000,4000],4,1)
    assert truth is True
    assert positions == [0,.16666666666666666,.6666666666666666,1]

def test_subsampled_axis_matches_display_stride():
    positions,truth=sampled_axis_positions([0,1,10,11,100,150],6,2)
    assert truth and positions==[0,.1,1]

def test_missing_unsorted_or_constant_axes_abstain():
    for axis in ([],[0,1],[0,2,1,3],[3,3,3,3]):
        positions,truth=sampled_axis_positions(axis,4,1)
        assert not truth and positions==[0,1/3,2/3,1]
