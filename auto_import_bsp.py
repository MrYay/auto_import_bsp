# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# This script automates calculating lightmap and lightgrid data for .bsp files in blender in the background
# This script requires the import_bsp addon developed by SomaZ (https://github.com/SomaZ/Blender_BSP_Importer)
# This script requires a valid .blend file where the .bsp has already been imported through the UI
# Quick usage: blender.exe -b blendfile.blend --python auto_import_bsp.py -- --bsp mapfile.bsp --lightmap --lightgrid
#
# Mr.Yeah! - 5/16/2025

import bpy
import import_bsp
from pathlib import Path


def cleanup_blend_file(gamepack_name=""):
    print('Blend file cleanup...')

    # Clear remaining lightmap images
    [bpy.data.images.remove(im) for im in bpy.data.images if "lm_" in im.filepath]

    # Clear previously imported sunext lights and game entities before reimport
    [bpy.data.objects.remove(obj) for obj in bpy.data.objects if "sunext" in obj.name]

    if gamepack_name == "":
        gamepack_name = bpy.context.preferences.addons['import_bsp'].preferences.gamepack

    gamepack_ents = import_bsp.idtech3lib.GamePacks.get_gamepack(
        bpy.utils.script_paths(subdir="addons/import_bsp/gamepacks/")[0],
        gamepack_name)

    for ent_name in gamepack_ents:
        for obj in bpy.data.objects:
            if obj.name == ent_name:
                bpy.data.objects.remove(obj)

    print('Blend file cleanup done')


def dummy_render():
    # render 1 dummy frame
    hidden_for_render = []
    temp_cam = None

    # Hide all objects except camera
    for obj in bpy.data.objects:
        if obj.type != 'CAMERA' and obj.hide_render == False:
            obj.hide_render = True
            hidden_for_render.append(obj)

    # Add temporary camera if not found
    if not len([obj for obj in bpy.data.objects if obj.type == 'CAMERA']):
        bpy.ops.object.camera_add()
        temp_cam = [obj for obj in bpy.data.objects if obj.type == 'CAMERA'][0]

    # Scene Render settings
    scene = bpy.data.scenes[0]
    previous_res_x = scene.render.resolution_x
    previous_res_y = scene.render.resolution_y
    previous_samples = scene.cycles.samples
    scene.render.resolution_x = 1
    scene.render.resolution_y = 1
    scene.cycles.samples = 1

    # Render 1 frame
    bpy.ops.render.render()

    # Scene cleanup
    scene.render.resolution_x = previous_res_x
    scene.render.resolution_y = previous_res_y
    scene.cycles.samples = previous_samples

    for hidden_obj in hidden_for_render:
        hidden_obj.hide_render = False

    if temp_cam is not None:
        bpy.data.objects.remove(temp_cam)


def bake_lightmap(bsp_path, patch_lightmap=False):
    def save_images(images_list, img_format="JPEG", suffix=".jpg"):
        for img in images_list:
            img.file_format = img_format
            img_path = Path(img.filepath)
            print(f"Saving image to {str(img_path.with_suffix(suffix))} ... ")
            img.save(filepath=str(img_path.with_suffix(suffix)), quality=90)

    # Select worldspawn
    bpy.context.view_layer.objects.active = bpy.data.objects['worldspawn']

    bpy.ops.q3.prepare_lm_baking()

    # Set Lightmap baking options
    bpy.data.scenes["Scene"].cycles.bake_type = 'DIFFUSE'
    bpy.data.scenes["Scene"].render.bake.use_pass_direct = True
    bpy.data.scenes["Scene"].render.bake.use_pass_indirect = True
    bpy.data.scenes["Scene"].render.bake.use_pass_color = False
    bpy.data.scenes["Scene"].render.bake.margin = 1

    # Bake Lightmap
    print('Baking Lightmap...')
    bpy.ops.object.bake(type='DIFFUSE')
    print('Lightmap baking done.')

    # Pack and Save Baked Images
    print('Packing lightmap images')
    bpy.ops.q3.pack_lightmap_images()

    # Look for external lightmaps
    lightmaps = [img for img in bpy.data.images if 'lm_' in img.filepath]
    if len(lightmaps) == 0:
        # No external lightmap found, use internal
        lightmaps = [img for img in bpy.data.images if '$lightmap_bake' in img.name]
        lightmaps[0].filepath = bpy.app.tempdir + lightmaps[0].name

    save_images(lightmaps, "OPEN_EXR", ".exr")

    # Prepare Lightmap compositing and export
    bpy.context.scene.node_tree.nodes.clear()

    outputfile_node = bpy.context.scene.node_tree.nodes.new("CompositorNodeOutputFile")
    outputfile_node.base_path = str(Path(lightmaps[0].filepath).parent)
    outputfile_node.format.file_format = 'JPEG'
    outputfile_node.format.quality = 98
    outputfile_node.location.x = 1000

    # Create 1 image + 1 denoise node per lightmap
    for index, lm in enumerate(lightmaps):
        lm_basename = Path(lm.filepath).stem
        image_node = bpy.context.scene.node_tree.nodes.new("CompositorNodeImage")
        image_node.image = lm
        image_node.location.y = index * -200
        denoise_node = bpy.context.scene.node_tree.nodes.new("CompositorNodeDenoise")
        denoise_node.prefilter = 'NONE'
        denoise_node.location.x = 600
        denoise_node.location.y = index * -200
        bpy.context.scene.node_tree.links.new(image_node.outputs["Image"], denoise_node.inputs["Image"])

        if len(outputfile_node.file_slots) - 1 < index:
            outputfile_node.file_slots.new(lm_basename)
        else:
            outputfile_node.file_slots[0].path = lm_basename
        bpy.context.scene.node_tree.links.new(denoise_node.outputs["Image"], outputfile_node.inputs[index])

    # Workaround to get the file output node to save lightmaps: render 1 dummy frame
    print('Denoising Lightmap...')
    dummy_render()

    # Rename saved lightmap files to remove frame number appended by the file output node
    lm_dir_files = [f for f in Path(lightmaps[0].filepath).parent.iterdir() if ".jpg" in str(f)]

    # Save external lightmap files
    for lm in lightmaps:
        lm_basename = Path(lm.filepath).stem
        lm_parent = Path(lm.filepath).parent
        # Ignore intermediary images (e.g .exr)
        for f in lm_dir_files:
            if lm_basename == f.stem:
                lm_dir_files.remove(f)
        # Find denoised lightmap file saved with frame number
        lm_filepath = [f for f in lm_dir_files if lm_basename in str(f)][0]

        # Create new lightmap file name
        new_lm_path = lm_parent.joinpath(lm_basename + '.jpg')

        # Rename lightmap file
        lm_filepath.replace(new_lm_path)
        # Delete the original lightmap
        if not ".jpg" in lm.filepath:
            Path(lm.filepath).unlink(missing_ok=True)

    # Patch .bsp file, lightmap only
    if patch_lightmap:
        # Handle internal lightmap
        if bpy.data.images.get("$lightmap_bake"):
            # Delete the original $lightmap_bake image, and reimport the denoised version
            bpy.data.images.load(bpy.data.images["$lightmap_bake"].filepath + ".jpg")
            bpy.data.images.remove(bpy.data.images["$lightmap_bake"])
            bpy.data.images['$lightmap_bake.jpg'].name = '$lightmap_bake'

        print('Patching BSP Lightmap...')
        bpy.ops.q3.patch_bsp_data(filepath=str(bsp_path), filter_glob="*.bsp", create_backup=False, patch_lm_tcs=True,
                                  patch_lightgrid=False, patch_lightmaps=True)
        print('BSP Lightmap patching done')
        return


def bake_lightgrid(bsp_path):
    # Create Lightgrid object
    print('Creating Lightgrid Object...')
    bpy.ops.q3.create_lightgrid()
    print('Lightgrid Object Created')

    # Select Lightgrid object only
    bpy.ops.object.select_all(action='DESELECT')
    bpy.data.objects['LightGrid'].select_set(True)
    bpy.context.view_layer.objects.active = bpy.data.objects['LightGrid']

    # Bake type diffuse, contributions direct+indirect, margin 0 px
    bpy.data.scenes["Scene"].cycles.bake_type = 'DIFFUSE'
    bpy.data.scenes["Scene"].render.bake.use_pass_direct = True
    bpy.data.scenes["Scene"].render.bake.use_pass_indirect = True
    bpy.data.scenes["Scene"].render.bake.use_pass_color = False
    bpy.data.scenes["Scene"].render.bake.margin = 0

    print('Baking Lightgrid...')
    bpy.ops.object.bake(type='DIFFUSE')
    print('Lightgrid baking done')

    # Convert baked lightgrid
    print('Converting Lightgrid...')
    bpy.ops.q3.convert_baked_lightgrid()
    print('Lightgrid converted')

    # Patch .bsp file, lightgrid only
    print('Patching BSP Lightgrid...')
    bpy.ops.q3.patch_bsp_data(filepath=str(bsp_path), filter_glob="*.bsp", create_backup=False, patch_lm_tcs=False,
                              patch_lightgrid=True, patch_lightmaps=False)
    print('BSP Lightgrid patching done')


def main():
    import sys  # to get command line args
    import argparse  # to parse options for us and print a nice help message

    # get the args passed to blender after "--", all of which are ignored by
    # blender so scripts may receive their own arguments
    argv = sys.argv

    if "--" not in argv:
        argv = []  # as if no args are passed
    else:
        argv = argv[argv.index("--") + 1:]  # get all args after "--"

    # When --help or no args are given, print this help
    usage_text = (
            "Run blender with the import_bsp addon in background mode on a blend file with this script:"
            "  blender --background </path/to/blendfile.blend> --python " + __file__ + " -- --bsp <path/to/mapname.bsp> [options]"
    )

    parser = argparse.ArgumentParser(description=usage_text)

    preset_choices = [
        "PREVIEW",
        "EDITING",
        "RENDERING",
        "BRUSHES",
        "SHADOW_BRUSHES",
        "ONLY_LIGHTS"
    ]

    atlas_size_choices = [
        "128",
        "256",
        "512",
        "1024",
        "2048"
    ]

    vert_map_packing_choices = [
        "Keep",
        "Primitive",
        "UVMap"
    ]

    parser.add_argument(
        "--bsp", dest="bsp", type=str, required=True, metavar="FILE",
        help="The .bsp file for which lighting will be baked",
    )
    parser.add_argument(
        "-p", "--preset", dest="preset", default="RENDERING", choices=preset_choices,
        help="BSP Import preset to use",
    )
    parser.add_argument(
        "--gamepack", dest="gamepack", type=str,
        help="Gamepack to use with import_bsp (default 'Jedi Knight Jedi Academy SP.json')",
    )
    parser.add_argument(
        "--subdivisions", dest="subdivisions", default="2", type=int,
        help="Amount of subdivisions to apply to patch meshes",
    )
    parser.add_argument(
        "--min-atlas-size", dest="min_atlas_size", default="2048", choices=atlas_size_choices,
        help="Minimum lightmap atlas square resolution, in pixels",
    )
    parser.add_argument(
        "--vert-map-packing", dest="vert_map_packing", default="Primitive", choices=vert_map_packing_choices,
        help="Changes UV unwrapping for vertex lit surfaces",
    )
    parser.add_argument(
        "--lightmap", dest="bake_lightmap", action="store_true",
        help="Enable Lightmap Baking",
    )
    parser.add_argument(
        "--patch-lm", dest="patch_lightmap", action="store_true",
        help="Enable .bsp Lightmap patching",
    )
    parser.add_argument(
        "--lightgrid", dest="bake_lightgrid", action="store_true",
        help="Enable Lightgrid Baking",
    )
    parser.add_argument(
        "--extra-emission-scale", dest="extra_emission_scale", type=float,
        help="Extra shader emission scale",
    )
    args = parser.parse_args(argv)

    if not argv:
        parser.print_help()
        return

    if not args.bsp:
        print("Error: --bsp <path/to/mapname.bsp> argument not given, aborting.")
        parser.print_help()
        return
    bsp_path = Path(args.bsp)
    print(f"bsp_path = {bsp_path}")
    if not bsp_path.exists():
        print(f"Error: BSP Path '{bsp_path}' does not exist, aborting")
        return

    if args.gamepack:
        gamepack_path = Path(bpy.utils.script_paths(subdir="addons/import_bsp/gamepacks/")[0] + args.gamepack)
        if not gamepack_path.exists():
            print(f"Error: Gamepack Path '{gamepack_path}' does not exist, aborting")
            return

    cleanup_blend_file(args.gamepack)
    bpy.ops.import_scene.id3_bsp(filepath=str(bsp_path), filter_glob="*.bsp", preset=args.preset,
                                 subdivisions=args.subdivisions, min_atlas_size=args.min_atlas_size,
                                 vert_map_packing=args.vert_map_packing)

    if args.extra_emission_scale:
        if "EmissionScaleNode" in [nodegroup.name for nodegroup in bpy.data.node_groups]:
            if "Extra emission scale" in [node.name for node in bpy.data.node_groups["EmissionScaleNode"].nodes]:
                print(f"Setting extra emission scale {args.extra_emission_scale}")
                bpy.data.node_groups["EmissionScaleNode"].nodes['Extra emission scale'].outputs[0].default_value = args.extra_emission_scale

    if args.bake_lightmap:
        bake_lightmap(bsp_path, args.patch_lightmap)
    if args.bake_lightgrid:
        bake_lightgrid(bsp_path)

    print("Job finished, exiting")


if __name__ == "__main__":
    main()
