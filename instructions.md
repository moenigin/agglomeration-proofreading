# Instructions:
The goal is to reconstruct whole cells in a segmentation by correcting mistakes of the agglomeration. Agglomeration mistakes are either false segment splits [fig1A] or false mergers [fig2B]. False segmentation mergers [fig2c] cannot be fixed with this tool but should be stored. 
Reconstruction starts with one segment, usually containing the soma. From there follow along one neurite and add falsely split segments [1.] and remove falsely merged segments [2./3.] 
## 1. merging false splits
* move the cursor above the falsely split segment and press 'q', try to target a location close to the target branch!
* move the cursor above the target branch close to the falsely split segment and press 'd'
## 2. splitting false agglomeration mergers:
* Move the cursor to one of the segments that is likely to be involved in the false merger and press 'c'. All segments connected to this segment are displayed:
    * If the segment is not merged to one in the wrong branch, hover over the next segment in the base volume and press 'c' again.
    * If a merged segment is found, move the cursor to this segment and split edges by pressing 'ctrl + x'. The viewer will refresh.
    * If the merged branches were successfully, hover over the segment/branch that does not belong to the target neuron and confirm the merge split by pressing 'k'.
## 3. removing groups of falsely merged segments:
This serves to remove larger groups of segments that should be split from the target branch. It does not preserve the connections of the segments to any other branch! This can be helpful to remove larger groups of segments covering membranes or ECS that are merged to the target neuron.
IMPORTANT: before using this, first make sure to empty the base volume viewport ('f')
* Select any segment in the base volume that should be removed. Press 'ctrl+bracketright' to split off the merged segments. The viewer updates and shows the segments in the neuron graph
* segments that do not belong to the neuron that is reconstructed can be removed by moving the cursor to the segment and pressing 'shift+f'
## 4. branch points:
* to set a branch point move the viewport location to the merge site (e.g. right click) and press 'y'
* to jump to the last unfinished branch location press '`'
* to tag a branch point as visited press 'ctrl + r'. It will be annotated with an ellipsoid and not be revisited when pressing '`'.
##5. storing segmentation merger locations:
* move the viewport center to the merge site (e.g. right click) and press 'm'
##6. storing misalignment locations:
* move the viewport center to the misaligned site (e.g. right click) and press 'p'
##Further keyboard shortcuts: 
* 'ctrl+a' with the cursor on a target segment will add the segment and its agglomerated partners to the neuron without adding an edge.
* 'shift+f' while hovering over a target segment will remove the segment __and__ its agglomerated partners from the neuron graph
* 'ctrl+z' undo function for merging edges, splitting edges, splitting of segment groups, adding segments to the neuron graph and deleting segments from the neuron graph. Only the last 10 actions can be undone
* 'w': toggle viewer layout between xy and the 3D view of both segmentation volumes and the the xy view and one of the segmentation volumes 
* '2'/'3': toggle segmentation layer opacity: '2' for the agglomerated volume and '3' for the base volume
* '4': toggle visibility of the (branch point) annotation layer with
* 'f' : to remove all selected segments from viewer of base volume
* 'n': to toggle the neuron display in the 3D agglomeration viewport
* 'ctrl+del' to exit review and close the browser window