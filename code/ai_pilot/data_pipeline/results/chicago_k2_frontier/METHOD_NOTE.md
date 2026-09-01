# Method note

The public temporal candidate universe is obtained without an assumed maximum
trip duration. For every core row, nearest-15-minute release error implies a
necessary overlap envelope in released start/end time. The live extractor pulls
all determinate K=2/match rows satisfying the union envelope and separately
counts/appends every K=2/match row with a null released start or end. This
closes the public timestamp candidate universe while leaving actual hidden-run
closure unidentified.
