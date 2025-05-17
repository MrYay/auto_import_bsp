# auto_import_bsp
This script automates calculating lightmap and lightgrid data for .bsp files using Blender in the background, based off the [import_bsp addon developped by SomaZ](https://github.com/SomaZ/Blender_BSP_Importer).

## Prerequisites
For now, as some GPU functions are unavailable when running Blender in background mode, this script needs versions of the `import_bsp` addon that bypass these GPU functions while in background mode, such as https://github.com/MrYay/Blender_BSP_Importer/tree/background

For the same reasons, a .blend file where the .bsp has been imported once through Blender's UI using the `import_bsp` addon is required. This is because the generation of the equirectangular image by `import_bsp` for the skybox can not be done in background mode.


## Quick usage

The script works with .bsp files that use external lightmaps. These can be generated from a source .map file using a compiler such as q3map2, which comes bundled with [netradiant-custom](https://github.com/Garux/netradiant-custom).


1.  A command line to compile a .bsp file along with external lightmaps can look like this (here using q3map2 from netradiant-custom):
  ```
  [path_to_q3map2] -meta -keeplights -samplesize 1 "[MapFile]"
  [path_to_q3map2] -light -fast -patchshadows -notrace -nocollapse -extlmhacksize 2048 "[MapFile]"
  ```
  This will generate a compiled .bsp alongside a folder with the same name as `[Mapfile]`, which will contain all external lightmap images to be used (these will be replaced when running `auto_import_bsp`).

2.  If not done already, a blendfile must be created and the resulting .bsp `[BspFile]` from the precedent step must be imported through Blender's UI using `import_bsp`, following the instructions [here](https://github.com/SomaZ/Blender_BSP_Importer/wiki/Importing-BSP-files) (use Import preset 'Rendering').

3.  Finally, to run the script and generate new lightmaps and lightgrid data using blender in background mode, the command below can be used with the `[BlendFile]` saved above:
    ```
    [path_to_blender_executable] -b "[BlendFile]" --python auto_import_bsp.py -- --bsp [BspFile] --lightmap --lightgrid
    ```


Step 2. only needs to be done once to have one .blend file per .bsp file.

Steps 1. and 3. can be combined in one sequence to be called in one click, for example through netradiant-custom's customizable Build Menu.
