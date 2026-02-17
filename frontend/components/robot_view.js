/**
 * Robot View - 2D factory map parsed from MuJoCo scene XML.
 * XML is embedded directly so the map always renders immediately.
 * Also tries to fetch live XML from server to pick up scene changes.
 */
var EMBEDDED_SCENE_XML = '<mujoco><asset><material name="lane_yellow" rgba="0.85 0.7 0.1 1"/><material name="shelf_metal" rgba="0.45 0.5 0.55 1"/><material name="shelf_beam" rgba="0.2 0.35 0.6 1"/><material name="box_cardboard" rgba="0.72 0.58 0.38 1"/><material name="box_blue" rgba="0.2 0.35 0.65 1"/><material name="box_red" rgba="0.7 0.15 0.1 1"/><material name="box_green" rgba="0.15 0.5 0.2 1"/><material name="pallet_wood" rgba="0.6 0.45 0.25 1"/><material name="wall_concrete" rgba="0.55 0.55 0.52 1"/><material name="pillar_concrete" rgba="0.5 0.5 0.48 1"/><material name="safety_stripe" rgba="0.9 0.75 0.0 1"/><material name="conveyor_belt" rgba="0.15 0.15 0.18 1"/><material name="conveyor_frame" rgba="0.4 0.4 0.42 1"/><material name="table_top" rgba="0.5 0.5 0.52 1"/><material name="unitree_dark" rgba="0.12 0.12 0.15 1"/><material name="unitree_silver" rgba="0.55 0.55 0.58 1"/><material name="unitree_accent" rgba="0.2 0.2 0.22 1"/></asset><worldbody><geom name="floor" type="plane" size="8 8 0.05" material="factory_floor"/><geom name="lane_center" type="box" size="0.05 4 0.001" pos="0 0 0.001" material="lane_yellow"/><geom name="lane_cross" type="box" size="4 0.05 0.001" pos="0 0 0.001" material="lane_yellow"/><geom name="wall_north" type="box" size="8 0.1 1.0" pos="0 7.5 1.0" material="wall_concrete"/><geom name="wall_south" type="box" size="8 0.1 1.0" pos="0 -5.5 1.0" material="wall_concrete"/><geom name="wall_east" type="box" size="0.1 6.5 1.0" pos="7.5 1.0 1.0" material="wall_concrete"/><geom name="wall_west" type="box" size="0.1 6.5 1.0" pos="-7.5 1.0 1.0" material="wall_concrete"/><geom name="pillar_1" type="box" size="0.15 0.15 2.0" pos="-4 -4 2.0" material="pillar_concrete"/><geom name="pillar_2" type="box" size="0.15 0.15 2.0" pos="4 -4 2.0" material="pillar_concrete"/><geom name="sA_upright_FL" type="box" size="0.03 0.03 1.5" pos="-4.1 -1.7 1.5" material="shelf_beam"/><geom name="sA_upright_FR" type="box" size="0.03 0.03 1.5" pos="-2.9 -1.7 1.5" material="shelf_beam"/><geom name="sA_upright_BL" type="box" size="0.03 0.03 1.5" pos="-4.1 -2.3 1.5" material="shelf_beam"/><geom name="sA_upright_BR" type="box" size="0.03 0.03 1.5" pos="-2.9 -2.3 1.5" material="shelf_beam"/><geom name="sA_shelf_1" type="box" size="0.65 0.35 0.015" pos="-3.5 -2 0.8" material="shelf_metal"/><geom name="sA_shelf_2" type="box" size="0.65 0.35 0.015" pos="-3.5 -2 1.6" material="shelf_metal"/><geom name="sA_shelf_3" type="box" size="0.65 0.35 0.015" pos="-3.5 -2 2.4" material="shelf_metal"/><geom name="sA_brace_1" type="box" size="0.6 0.01 0.01" pos="-3.5 -2.3 1.2" material="shelf_beam"/><geom name="sA_brace_2" type="box" size="0.6 0.01 0.01" pos="-3.5 -2.3 2.0" material="shelf_beam"/><geom name="sA_box1" type="box" size="0.15 0.12 0.12" pos="-3.75 -2 0.93" material="box_cardboard"/><geom name="sA_box2" type="box" size="0.12 0.1 0.1" pos="-3.25 -2 0.91" material="box_blue"/><geom name="sA_box3" type="box" size="0.2 0.15 0.1" pos="-3.5 -2 1.72" material="box_red"/><geom name="sA_box4" type="box" size="0.1 0.1 0.1" pos="-3.7 -2 2.52" material="box_green"/><geom name="sB_upright_FL" type="box" size="0.03 0.03 1.5" pos="2.9 -1.7 1.5" material="shelf_beam"/><geom name="sB_upright_FR" type="box" size="0.03 0.03 1.5" pos="4.1 -1.7 1.5" material="shelf_beam"/><geom name="sB_upright_BL" type="box" size="0.03 0.03 1.5" pos="2.9 -2.3 1.5" material="shelf_beam"/><geom name="sB_upright_BR" type="box" size="0.03 0.03 1.5" pos="4.1 -2.3 1.5" material="shelf_beam"/><geom name="sB_shelf_1" type="box" size="0.65 0.35 0.015" pos="3.5 -2 0.8" material="shelf_metal"/><geom name="sB_shelf_2" type="box" size="0.65 0.35 0.015" pos="3.5 -2 1.6" material="shelf_metal"/><geom name="sB_shelf_3" type="box" size="0.65 0.35 0.015" pos="3.5 -2 2.4" material="shelf_metal"/><geom name="sB_brace_1" type="box" size="0.6 0.01 0.01" pos="3.5 -2.3 1.2" material="shelf_beam"/><geom name="sB_brace_2" type="box" size="0.6 0.01 0.01" pos="3.5 -2.3 2.0" material="shelf_beam"/><geom name="sB_box1" type="box" size="0.18 0.14 0.11" pos="3.5 -2 0.92" material="box_cardboard"/><geom name="sB_box2" type="box" size="0.1 0.1 0.08" pos="3.8 -2 0.9" material="box_blue"/><geom name="sB_box3" type="box" size="0.15 0.12 0.12" pos="3.35 -2 1.73" material="box_red"/><geom name="sB_box4" type="box" size="0.12 0.12 0.15" pos="3.7 -2 1.77" material="box_green"/><geom name="conv_leg_1" type="box" size="0.04 0.04 0.35" pos="-1.5 -3.75 0.35" material="conveyor_frame"/><geom name="conv_leg_2" type="box" size="0.04 0.04 0.35" pos="1.5 -3.75 0.35" material="conveyor_frame"/><geom name="conv_leg_3" type="box" size="0.04 0.04 0.35" pos="-1.5 -3.25 0.35" material="conveyor_frame"/><geom name="conv_leg_4" type="box" size="0.04 0.04 0.35" pos="1.5 -3.25 0.35" material="conveyor_frame"/><geom name="conv_belt" type="box" size="1.6 0.3 0.02" pos="0 -3.5 0.72" material="conveyor_belt"/><geom name="conv_rail_L" type="box" size="1.6 0.02 0.05" pos="0 -3.2 0.77" material="conveyor_frame"/><geom name="conv_rail_R" type="box" size="1.6 0.02 0.05" pos="0 -3.8 0.77" material="conveyor_frame"/><geom name="conv_box1" type="box" size="0.12 0.1 0.08" pos="-0.8 -3.5 0.82" material="box_cardboard"/><geom name="conv_box2" type="box" size="0.1 0.08 0.1" pos="0 -3.5 0.84" material="box_blue"/><geom name="conv_box3" type="box" size="0.14 0.12 0.09" pos="0.7 -3.5 0.83" material="box_red"/><geom name="table_leg_1" type="cylinder" size="0.03 0.4" pos="1.55 1.2 0.4" material="conveyor_frame"/><geom name="table_leg_2" type="cylinder" size="0.03 0.4" pos="2.45 1.2 0.4" material="conveyor_frame"/><geom name="table_leg_3" type="cylinder" size="0.03 0.4" pos="1.55 1.8 0.4" material="conveyor_frame"/><geom name="table_leg_4" type="cylinder" size="0.03 0.4" pos="2.45 1.8 0.4" material="conveyor_frame"/><geom name="table_surface" type="box" size="0.5 0.35 0.02" pos="2 1.5 0.82" material="table_top"/><geom name="table_box1" type="box" size="0.06 0.06 0.04" pos="1.8 1.5 0.88" material="box_green"/><geom name="table_box2" type="box" size="0.08 0.05 0.05" pos="2.15 1.6 0.89" material="box_blue"/><geom name="pallet_1" type="box" size="0.5 0.4 0.05" pos="-1.5 1 0.05" material="pallet_wood"/><geom name="p1_box1" type="box" size="0.2 0.18 0.1" pos="-1.65 1 0.2" material="box_cardboard"/><geom name="p1_box2" type="box" size="0.18 0.16 0.12" pos="-1.3 1 0.22" material="box_cardboard"/><geom name="p1_box3" type="box" size="0.22 0.18 0.1" pos="-1.5 1 0.42" material="box_red"/><geom name="pallet_2" type="box" size="0.5 0.4 0.05" pos="1.5 1 0.05" material="pallet_wood"/><geom name="bollard_1" type="cylinder" size="0.06 0.4" pos="-2 0.5 0.4" material="safety_stripe"/><geom name="bollard_2" type="cylinder" size="0.06 0.4" pos="-2 -0.5 0.4" material="safety_stripe"/><geom name="bollard_3" type="cylinder" size="0.06 0.4" pos="2 0.5 0.4" material="safety_stripe"/><geom name="bollard_4" type="cylinder" size="0.06 0.4" pos="2 -0.5 0.4" material="safety_stripe"/><geom name="sg1a_head" type="sphere" size="0.08" pos="0 0 1.32" material="unitree_dark"/><geom name="sg1a_torso" type="box" size="0.08 0.1 0.18" pos="0 0 1.0" material="unitree_silver"/><geom name="sg1a_pelvis" type="box" size="0.07 0.12 0.06" pos="0 0 0.76" material="unitree_dark"/><geom name="sg1a_lleg_u" type="capsule" size="0.045" material="unitree_accent"/><geom name="sg1a_lleg_l" type="capsule" size="0.038" material="unitree_dark"/><geom name="sg1a_rleg_u" type="capsule" size="0.045" material="unitree_accent"/><geom name="sg1a_rleg_l" type="capsule" size="0.038" material="unitree_dark"/><geom name="sg1a_lfoot" type="box" size="0.06 0.03 0.012" pos="0.02 0.065 0.012" material="unitree_dark"/><geom name="sg1a_rfoot" type="box" size="0.06 0.03 0.012" pos="0.02 -0.065 0.012" material="unitree_dark"/><geom name="sg1a_larm" type="capsule" size="0.028" material="unitree_accent"/><geom name="sg1a_rarm" type="capsule" size="0.028" material="unitree_accent"/><geom name="sg1b_head" type="sphere" size="0.08" pos="0 0 1.32" material="unitree_dark"/><geom name="sg1b_torso" type="box" size="0.08 0.1 0.18" pos="0 0 1.0" material="unitree_silver"/><geom name="sg1b_pelvis" type="box" size="0.07 0.12 0.06" pos="0 0 0.76" material="unitree_dark"/><geom name="sg1b_lleg_u" type="capsule" size="0.045" material="unitree_accent"/><geom name="sg1b_lleg_l" type="capsule" size="0.038" material="unitree_dark"/><geom name="sg1b_rleg_u" type="capsule" size="0.045" material="unitree_accent"/><geom name="sg1b_rleg_l" type="capsule" size="0.038" material="unitree_dark"/><geom name="sg1b_lfoot" type="box" size="0.06 0.03 0.012" pos="0.02 0.065 0.012" material="unitree_dark"/><geom name="sg1b_rfoot" type="box" size="0.06 0.03 0.012" pos="0.02 -0.065 0.012" material="unitree_dark"/><geom name="sg1b_larm" type="capsule" size="0.028" material="unitree_accent"/><geom name="sg1b_rarm" type="capsule" size="0.028" material="unitree_accent"/><geom name="sg1c_head" type="sphere" size="0.08" pos="0 0 1.32" material="unitree_dark"/><geom name="sg1c_torso" type="box" size="0.08 0.1 0.18" pos="0 0 1.0" material="unitree_silver"/><geom name="sg1c_pelvis" type="box" size="0.07 0.12 0.06" pos="0 0 0.76" material="unitree_dark"/><geom name="sg1c_lleg_u" type="capsule" size="0.045" material="unitree_accent"/><geom name="sg1c_lleg_l" type="capsule" size="0.038" material="unitree_dark"/><geom name="sg1c_rleg_u" type="capsule" size="0.045" material="unitree_accent"/><geom name="sg1c_rleg_l" type="capsule" size="0.038" material="unitree_dark"/><geom name="sg1c_lfoot" type="box" size="0.06 0.03 0.012" pos="0.02 0.065 0.012" material="unitree_dark"/><geom name="sg1c_rfoot" type="box" size="0.06 0.03 0.012" pos="0.02 -0.065 0.012" material="unitree_dark"/><geom name="sg1c_larm" type="capsule" size="0.028" material="unitree_accent"/><geom name="sg1c_rarm" type="capsule" size="0.028" material="unitree_accent"/><geom name="go2a_body" type="box" size="0.19 0.065 0.055" pos="0 0 0.33" material="unitree_dark"/><geom name="go2a_head" type="box" size="0.05 0.04 0.035" pos="0.22 0 0.35" material="unitree_accent"/><geom name="go2a_lidar" type="cylinder" size="0.035 0.02" pos="0.2 0 0.41" material="unitree_silver"/><geom name="go2a_fl" type="capsule" size="0.018" material="unitree_accent"/><geom name="go2a_fr" type="capsule" size="0.018" material="unitree_accent"/><geom name="go2a_bl" type="capsule" size="0.018" material="unitree_accent"/><geom name="go2a_br" type="capsule" size="0.018" material="unitree_accent"/><geom name="go2b_body" type="box" size="0.19 0.065 0.055" pos="0 0 0.33" material="unitree_dark"/><geom name="go2b_head" type="box" size="0.05 0.04 0.035" pos="0.22 0 0.35" material="unitree_accent"/><geom name="go2b_lidar" type="cylinder" size="0.035 0.02" pos="0.2 0 0.41" material="unitree_silver"/><geom name="go2b_fl" type="capsule" size="0.018" material="unitree_accent"/><geom name="go2b_fr" type="capsule" size="0.018" material="unitree_accent"/><geom name="go2b_bl" type="capsule" size="0.018" material="unitree_accent"/><geom name="go2b_br" type="capsule" size="0.018" material="unitree_accent"/><geom name="charge_platform" type="box" size="0.6 0.6 0.1" pos="-5.5 3.5 0.1" material="conveyor_frame"/><geom name="charge_pad" type="box" size="0.3 0.3 0.02" pos="-5.5 3.5 0.22" rgba="0.1 0.8 0.1 0.8"/><geom name="charge_pole" type="cylinder" size="0.04 0.5" pos="-5.5 4.1 0.5" material="conveyor_frame"/><geom name="cabinet_body" type="box" size="0.4 0.25 0.6" pos="5.5 -0.5 0.6" material="shelf_metal"/><geom name="cabinet_top" type="box" size="0.42 0.27 0.02" pos="5.5 -0.5 1.22" material="shelf_metal"/><geom name="cabinet_tool1" type="box" size="0.06 0.04 0.03" pos="5.35 -0.5 1.27" rgba="0.6 0.3 0.1 1"/><geom name="cabinet_tool2" type="box" size="0.05 0.05 0.02" pos="5.65 -0.45 1.26" rgba="0.3 0.3 0.6 1"/><geom name="storage_rack" type="box" size="0.8 0.4 1.2" pos="-5.0 -3.5 1.2" material="shelf_beam"/><geom name="storage_shelf_1" type="box" size="0.78 0.38 0.015" pos="-5.0 -3.5 0.8" material="shelf_metal"/><geom name="storage_shelf_2" type="box" size="0.78 0.38 0.015" pos="-5.0 -3.5 1.6" material="shelf_metal"/><geom name="storage_box1" type="box" size="0.2 0.15 0.12" pos="-5.2 -3.5 0.93" material="box_cardboard"/><geom name="storage_box2" type="box" size="0.15 0.12 0.1" pos="-4.75 -3.5 0.92" material="box_blue"/><geom name="storage_box3" type="box" size="0.18 0.14 0.1" pos="-5.1 -3.5 1.72" material="box_red"/><geom name="storage_box4" type="box" size="0.12 0.12 0.12" pos="-4.8 -3.5 1.73" material="box_green"/><geom name="inspect_table" type="box" size="0.6 0.4 0.4" pos="0.0 4.5 0.4" material="table_top"/><geom name="inspect_light" type="sphere" size="0.1" pos="0.0 4.5 1.5" rgba="0.9 0.9 0.3 0.6"/><geom name="inspect_pad" type="box" size="0.4 0.3 0.01" pos="0.0 4.5 0.82" rgba="0.2 0.6 0.8 0.5"/><geom name="status_light" type="sphere" size="0.08" pos="0 0 10"/><geom name="wp_marker_0" type="cylinder" size="0.35 0.003" pos="-3.5 -2.0 0.002"/><geom name="wp_marker_1" type="cylinder" size="0.35 0.003" pos="3.5 -2.0 0.002"/><geom name="wp_marker_2" type="cylinder" size="0.35 0.003" pos="0.0 -3.5 0.002"/><geom name="wp_marker_3" type="cylinder" size="0.35 0.003" pos="2.0 1.5 0.002"/><geom name="wp_marker_4" type="cylinder" size="0.35 0.003" pos="-1.5 1.0 0.002"/><geom name="wp_marker_5" type="cylinder" size="0.35 0.003" pos="1.5 1.0 0.002"/><geom name="wp_marker_6" type="cylinder" size="0.35 0.003" pos="-5.5 3.5 0.002"/><geom name="wp_marker_7" type="cylinder" size="0.35 0.003" pos="5.5 -0.5 0.002"/><geom name="wp_marker_8" type="cylinder" size="0.35 0.003" pos="-5.0 -3.5 0.002"/><geom name="wp_marker_9" type="cylinder" size="0.35 0.003" pos="0.0 4.5 0.002"/><geom name="trail_0" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_1" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_2" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_3" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_4" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_5" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_6" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_7" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_8" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_9" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_10" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_11" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_12" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_13" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_14" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_15" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_16" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_17" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_18" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_19" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_20" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_21" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_22" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_23" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_24" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_25" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_26" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_27" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_28" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_29" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_30" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_31" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_32" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_33" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_34" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_35" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_36" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_37" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_38" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_39" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_40" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_41" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_42" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_43" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_44" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_45" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_46" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_47" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_48" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_49" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_50" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_51" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_52" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_53" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_54" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_55" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_56" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_57" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_58" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_59" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_60" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_61" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_62" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_63" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_64" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_65" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_66" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_67" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_68" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_69" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_70" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_71" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_72" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_73" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_74" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_75" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_76" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_77" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_78" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_79" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_80" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_81" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_82" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_83" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_84" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_85" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_86" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_87" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_88" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_89" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_90" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_91" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_92" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_93" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_94" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_95" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_96" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_97" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_98" type="cylinder" size="0.04 0.002" pos="0 0 -1"/><geom name="trail_99" type="cylinder" size="0.04 0.002" pos="0 0 -1"/></worldbody></mujoco>';

function RobotView(canvasId) {
    this.canvas = document.getElementById(canvasId);
    if (!this.canvas) { console.error("[RobotView] Canvas not found:", canvasId); return; }
    this.ctx = this.canvas.getContext("2d");
    this.robot = { x: 0, y: 0, angle: 0, trail: [] };
    this.navTarget = null; // { x, y, name } set by app.js from nav_update
    this.viewRange = 5;
    this.minViewRange = 2;
    this.maxViewRange = 12;
    this.followRobot = true;
    this.mapObjects = [];
    this.materials = {};
    this.floorSize = [8, 8];
    this.mapLoaded = false;
    this.legendCategories = {};
    // Multi-robot state
    this.allRobots = []; // [{id, position, orientation, color, selected, ...}]
    this.selectedRobotId = "robot_0";
    this.onRobotClick = null; // callback(robotId) set by app.js
    this._resize();
    var self = this;
    window.addEventListener("resize", function() { self._resize(); });
    this.canvas.addEventListener("wheel", function(e) {
        e.preventDefault();
        var delta = e.deltaY > 0 ? 0.5 : -0.5;
        self.viewRange = Math.max(self.minViewRange, Math.min(self.maxViewRange, self.viewRange + delta));
    }, { passive: false });
    // Click-to-select robot
    this.canvas.addEventListener("click", function(e) {
        self._handleClick(e);
    });
    this._parseSceneXML(EMBEDDED_SCENE_XML);
    this.mapLoaded = true;
    console.log("[RobotView] Map loaded from embedded XML:", this.mapObjects.length, "objects");
    this._tryFetchLiveXML();
    this._draw();
}

RobotView.prototype._resize = function() {
    var rect = this.canvas.parentElement.getBoundingClientRect();
    this.canvas.width = Math.max(100, rect.width);
    this.canvas.height = Math.max(100, rect.height - 30);
};

RobotView.prototype._tryFetchLiveXML = function() {
    var self = this;
    if (typeof fetch === "undefined") return;
    fetch("/scenes/factory_scene.xml").then(function(r) {
        if (r.ok) return r.text(); throw new Error("fail");
    }).then(function(xml) {
        self._parseSceneXML(xml);
        self.mapLoaded = true;
        console.log("[RobotView] Updated from live XML:", self.mapObjects.length, "objects");
    }).catch(function() {});
};

RobotView.prototype._parseSceneXML = function(xmlText) {
    var parser = new DOMParser();
    var doc = parser.parseFromString(xmlText, "text/xml");
    if (doc.querySelector("parsererror")) { console.error("[RobotView] XML parse error"); return; }
    this.materials = {};
    var mats = doc.querySelectorAll("material");
    for (var i = 0; i < mats.length; i++) {
        var mat = mats[i], name = mat.getAttribute("name"), rgbaStr = mat.getAttribute("rgba");
        if (!name || !rgbaStr) continue;
        var rgba = rgbaStr.split(/\s+/).map(Number);
        this.materials[name] = { rgba: rgba, hex: this._rgbaToHex(rgba) };
    }
    this.mapObjects = []; this.floorSize = [8, 8];
    var geoms = doc.querySelectorAll("geom");
    for (var j = 0; j < geoms.length; j++) {
        var g = geoms[j];
        var gn = g.getAttribute("name") || "", gt = g.getAttribute("type") || "sphere";
        var gm = g.getAttribute("material") || "";
        var pos = (g.getAttribute("pos") || "0 0 0").split(/\s+/).map(Number);
        while (pos.length < 3) pos.push(0);
        var size = (g.getAttribute("size") || "0.1").split(/\s+/).map(Number);
        var mi = this.materials[gm];
        var rgba2 = mi ? mi.rgba : [0.5,0.5,0.5,1]; var hex = mi ? mi.hex : "#808080";
        var cat = this._categorize(gn, gm);
        if (gt === "plane") { if (size.length >= 2) this.floorSize = [size[0], size[1]]; continue; }
        var obj = { name:gn, type:gt, category:cat, rgba:rgba2, hex:hex, x:pos[0], y:pos[1], z:pos[2] };
        if (gt === "box") { obj.w = (size[0]||0.1)*2; obj.h = (size[1]||0.1)*2; }
        else if (gt === "cylinder") { obj.r = size[0]||0.1; }
        this.mapObjects.push(obj);
    }
    this.mapObjects.sort(function(a,b) { return a.z - b.z; });
    this._buildLegend();
};

RobotView.prototype._rgbaToHex = function(rgba) {
    function h(v) { return Math.round(Math.min(1,Math.max(0,v))*255).toString(16).padStart(2,"0"); }
    return "#" + h(rgba[0]) + h(rgba[1]) + h(rgba[2]);
};

RobotView.prototype._categorize = function(name, material) {
    var n = name.toLowerCase(), m = material.toLowerCase();
    if (n.indexOf("wall") >= 0) return "wall";
    if (n.indexOf("pillar") >= 0) return "pillar";
    if (n.indexOf("lane") >= 0) return "lane";
    if (n.indexOf("sa_") === 0 || n.indexOf("sb_") === 0) {
        if (n.indexOf("upright") >= 0 || n.indexOf("brace") >= 0) return "shelf_frame";
        if (n.indexOf("shelf") >= 0) return "shelf";
        if (n.indexOf("box") >= 0) return "box";
    }
    if (n.indexOf("conv") >= 0) {
        if (n.indexOf("belt") >= 0) return "conveyor";
        if (n.indexOf("rail") >= 0 || n.indexOf("leg") >= 0) return "conveyor_frame";
        if (n.indexOf("box") >= 0) return "box";
    }
    if (n.indexOf("table") >= 0) {
        if (n.indexOf("surface") >= 0 || n.indexOf("top") >= 0) return "table";
        if (n.indexOf("leg") >= 0) return "table_leg";
        if (n.indexOf("box") >= 0) return "box";
    }
    if (n.indexOf("pallet") >= 0 && n.indexOf("box") < 0) return "pallet";
    if (n.indexOf("p1_") === 0 || n.indexOf("p2_") === 0) return "box";
    if (n.indexOf("bollard") >= 0) return "bollard";
    if (n.indexOf("box") >= 0 || m.indexOf("box") >= 0) return "box";
    if (n.indexOf("charge") >= 0 || n.indexOf("charging") >= 0) return "charging_station";
    if (n.indexOf("cabinet") >= 0) return "tool_cabinet";
    if (n.indexOf("storage") >= 0 && n.indexOf("box") < 0) return "storage_rack";
    if (n.indexOf("inspect") >= 0) return "inspection_zone";
    return "other";
};

RobotView.prototype._buildLegend = function() {
    this.legendCategories = {};
    for (var i = 0; i < this.mapObjects.length; i++) {
        var o = this.mapObjects[i];
        if (!this.legendCategories[o.category]) this.legendCategories[o.category] = o.hex;
    }
};

RobotView.prototype.reset = function() {
    this.robot.x = 0;
    this.robot.y = 0;
    this.robot.angle = 0;
    this.robot.trail = [];
};

RobotView.prototype.updateState = function(robotState, action, allRobots, selectedRobotId) {
    // Store multi-robot data if provided
    if (allRobots && allRobots.length > 0) {
        this.allRobots = allRobots;
        this.selectedRobotId = selectedRobotId || "robot_0";
    }

    // Use real sim position if available (non-zero position means sim is running)
    if (robotState && robotState.position &&
        (robotState.position[0] !== 0 || robotState.position[1] !== 0 || robotState.orientation !== 0)) {
        this.robot.x = robotState.position[0];
        this.robot.y = robotState.position[1];
        this.robot.angle = robotState.orientation || 0;
    } else {
        // Fallback: dead-reckoning for stub mode (no sim)
        if (!action || action === "IDLE") return;
        var s = 0.06, r = 0.06;
        if (action === "MOVE_FORWARD") { this.robot.x += Math.cos(this.robot.angle)*s; this.robot.y += Math.sin(this.robot.angle)*s; }
        if (action === "MOVE_BACKWARD") { this.robot.x -= Math.cos(this.robot.angle)*s; this.robot.y -= Math.sin(this.robot.angle)*s; }
        if (action === "ROTATE_LEFT") this.robot.angle += r;
        if (action === "ROTATE_RIGHT") this.robot.angle -= r;
        var mx = this.floorSize[0]-0.5, my = this.floorSize[1]-0.5;
        this.robot.x = Math.max(-mx, Math.min(mx, this.robot.x));
        this.robot.y = Math.max(-my, Math.min(my, this.robot.y));
    }
    this.robot.trail.push({ x: this.robot.x, y: this.robot.y });
    if (this.robot.trail.length > 500) this.robot.trail.shift();
};

RobotView.prototype._toC = function(wx, wy, scale, cx, cy) {
    if (this.followRobot) return { x: cx+(wx-this.robot.x)*scale, y: cy-(wy-this.robot.y)*scale };
    return { x: cx+wx*scale, y: cy-wy*scale };
};

RobotView.prototype._draw = function() {
    var self = this;
    try { this._drawFrame(); } catch(e) { console.error("[RobotView]", e); }
    requestAnimationFrame(function() { self._draw(); });
};

RobotView.prototype._drawFrame = function() {
    var ctx = this.ctx, w = this.canvas.width, h = this.canvas.height;
    if (w < 10 || h < 10) return;
    var cx = w/2, cy = h/2, scale = Math.min(w,h)/(this.viewRange*2);
    var self = this;
    function toC(wx,wy) { return self._toC(wx,wy,scale,cx,cy); }
    ctx.fillStyle = "#1a1e24"; ctx.fillRect(0,0,w,h);
    ctx.strokeStyle = "#222830"; ctx.lineWidth = 0.5;
    var ge = Math.max(this.floorSize[0], this.floorSize[1]);
    for (var i = -ge; i <= ge; i++) {
        var p1=toC(i,-ge), p2=toC(i,ge); ctx.beginPath(); ctx.moveTo(p1.x,p1.y); ctx.lineTo(p2.x,p2.y); ctx.stroke();
        p1=toC(-ge,i); p2=toC(ge,i); ctx.beginPath(); ctx.moveTo(p1.x,p1.y); ctx.lineTo(p2.x,p2.y); ctx.stroke();
    }
    if (this.mapLoaded) { for (var j=0; j<this.mapObjects.length; j++) this._drawObj(ctx,this.mapObjects[j],scale,toC); }
    if (this.robot.trail.length > 1) {
        ctx.strokeStyle = "rgba(6,182,212,0.15)"; ctx.lineWidth = Math.max(2,scale*0.05); ctx.beginPath();
        for (var k=0; k<this.robot.trail.length; k++) { var pt=toC(this.robot.trail[k].x,this.robot.trail[k].y); k===0?ctx.moveTo(pt.x,pt.y):ctx.lineTo(pt.x,pt.y); }
        ctx.stroke();
    }
    // Draw navigation target if active
    if (this.navTarget) this._drawNavTarget(ctx, scale, toC);
    // Draw all robots (non-selected first, then selected on top)
    if (this.allRobots.length > 0) {
        for (var ri = 0; ri < this.allRobots.length; ri++) {
            if (!this.allRobots[ri].selected) this._drawMultiRobot(ctx, scale, toC, this.allRobots[ri]);
        }
        for (var ri2 = 0; ri2 < this.allRobots.length; ri2++) {
            if (this.allRobots[ri2].selected) this._drawMultiRobot(ctx, scale, toC, this.allRobots[ri2]);
        }
    } else {
        this._drawRobot(ctx,scale,toC);
    }
    this._drawHUD(ctx,w,h,scale);
    if (this.mapLoaded) this._drawLegend(ctx,w,h);
};

RobotView.prototype._drawObj = function(ctx, obj, scale, toC) {
    var cat = obj.category, color = obj.hex;
    if (cat === "lane") {
        var hw=(obj.w||0.1)/2, hh=(obj.h||0.1)/2, vert=hh>hw;
        var lr=Math.round(obj.rgba[0]*255), lg=Math.round(obj.rgba[1]*255), lb=Math.round(obj.rgba[2]*255);
        ctx.strokeStyle = "rgba("+lr+","+lg+","+lb+",0.35)";
        ctx.lineWidth = 3; ctx.setLineDash([scale*0.3, scale*0.2]);
        var lp1,lp2; if (vert) { lp1=toC(obj.x,obj.y-hh); lp2=toC(obj.x,obj.y+hh); } else { lp1=toC(obj.x-hw,obj.y); lp2=toC(obj.x+hw,obj.y); }
        ctx.beginPath(); ctx.moveTo(lp1.x,lp1.y); ctx.lineTo(lp2.x,lp2.y); ctx.stroke(); ctx.setLineDash([]); return;
    }
    if (obj.type === "box") {
        var ow=obj.w||0.2, oh=obj.h||0.2, wp=ow*scale, hp=oh*scale, p=toC(obj.x-ow/2, obj.y+oh/2);
        if (cat==="wall") { ctx.fillStyle=color; ctx.fillRect(p.x,p.y,wp,hp); this._label(ctx,toC(obj.x,obj.y),"WALL","#999",scale); }
        else if (cat==="pillar") { ctx.fillStyle=color; ctx.fillRect(p.x,p.y,wp,hp); ctx.strokeStyle="#777"; ctx.lineWidth=1; ctx.strokeRect(p.x,p.y,wp,hp); }
        else if (cat==="shelf") { ctx.fillStyle="rgba(0,0,0,0.3)"; ctx.fillRect(p.x+2,p.y+2,wp,hp); ctx.fillStyle=color; ctx.fillRect(p.x,p.y,wp,hp); ctx.strokeStyle=this._lighten(color,0.3); ctx.lineWidth=1; ctx.strokeRect(p.x,p.y,wp,hp); var sl=obj.name.indexOf("sA")===0?"SHELF A":"SHELF B"; this._label(ctx,toC(obj.x,obj.y),sl,"#8ab4f8",scale); }
        else if (cat==="shelf_frame") { ctx.fillStyle=color; ctx.fillRect(p.x,p.y,wp,hp); }
        else if (cat==="conveyor") { ctx.fillStyle=color; ctx.fillRect(p.x,p.y,wp,hp); ctx.strokeStyle=this._lighten(color,0.15); ctx.lineWidth=1; var rc=Math.max(3,Math.floor(wp/12)); for(var ri=1;ri<rc;ri++){var rx=p.x+wp*ri/rc;ctx.beginPath();ctx.moveTo(rx,p.y);ctx.lineTo(rx,p.y+hp);ctx.stroke();} this._label(ctx,toC(obj.x,obj.y),"CONVEYOR","#888",scale); }
        else if (cat==="conveyor_frame") { ctx.fillStyle=color; ctx.fillRect(p.x,p.y,wp,hp); }
        else if (cat==="table") { ctx.fillStyle=color; ctx.fillRect(p.x,p.y,wp,hp); ctx.strokeStyle="#777"; ctx.lineWidth=1; ctx.strokeRect(p.x,p.y,wp,hp); this._label(ctx,toC(obj.x,obj.y),"TABLE","#888",scale); }
        else if (cat==="table_leg") { ctx.fillStyle=color; ctx.fillRect(p.x,p.y,wp,hp); }
        else if (cat==="pallet") { ctx.fillStyle=color; ctx.fillRect(p.x,p.y,wp,hp); ctx.strokeStyle=this._darken(color,0.2); ctx.lineWidth=1; for(var si=1;si<4;si++){var sy=p.y+hp*si/4;ctx.beginPath();ctx.moveTo(p.x,sy);ctx.lineTo(p.x+wp,sy);ctx.stroke();} var pl=obj.name.indexOf("1")>=0?"PALLET-SRC":"PALLET-DST"; this._label(ctx,toC(obj.x,obj.y),pl,"#ccc",scale); }
        else if (cat==="box") { var cp=toC(obj.x,obj.y),br=Math.max(2,scale*0.08); ctx.fillStyle=color; ctx.beginPath(); ctx.arc(cp.x,cp.y,br,0,Math.PI*2); ctx.fill(); }
        else if (cat==="charging_station") { ctx.fillStyle="rgba(16,185,16,0.25)"; ctx.fillRect(p.x,p.y,wp,hp); ctx.strokeStyle="#10b981"; ctx.lineWidth=2; ctx.strokeRect(p.x,p.y,wp,hp); this._label(ctx,toC(obj.x,obj.y),"CHARGING","#10b981",scale); }
        else if (cat==="tool_cabinet") { ctx.fillStyle=color; ctx.fillRect(p.x,p.y,wp,hp); ctx.strokeStyle="#94a3b8"; ctx.lineWidth=1; ctx.strokeRect(p.x,p.y,wp,hp); this._label(ctx,toC(obj.x,obj.y),"CABINET","#94a3b8",scale); }
        else if (cat==="storage_rack") { ctx.fillStyle=color; ctx.fillRect(p.x,p.y,wp,hp); ctx.strokeStyle=this._lighten(color,0.2); ctx.lineWidth=1; ctx.strokeRect(p.x,p.y,wp,hp); this._label(ctx,toC(obj.x,obj.y),"STORAGE","#8ab4f8",scale); }
        else if (cat==="inspection_zone") { ctx.fillStyle="rgba(32,150,200,0.2)"; ctx.fillRect(p.x,p.y,wp,hp); ctx.strokeStyle="#06b6d4"; ctx.lineWidth=2; ctx.strokeRect(p.x,p.y,wp,hp); this._label(ctx,toC(obj.x,obj.y),"INSPECT","#06b6d4",scale); }
        else { ctx.fillStyle=color; ctx.fillRect(p.x,p.y,wp,hp); }
    } else if (obj.type === "cylinder") {
        var ccp=toC(obj.x,obj.y), cr=obj.r||0.1;
        if (cat==="bollard") { var brp=Math.max(3,cr*scale*3); ctx.fillStyle=color; ctx.beginPath(); ctx.arc(ccp.x,ccp.y,brp,0,Math.PI*2); ctx.fill(); ctx.fillStyle="#222"; ctx.beginPath(); ctx.arc(ccp.x,ccp.y,brp*0.5,0,Math.PI*2); ctx.fill(); }
        else { var crp=Math.max(2,cr*scale); ctx.fillStyle=color; ctx.beginPath(); ctx.arc(ccp.x,ccp.y,crp,0,Math.PI*2); ctx.fill(); }
    }
};

RobotView.prototype._label = function(ctx,pos,text,color,scale) {
    ctx.fillStyle=color; ctx.font=Math.max(9,scale*0.22)+"px JetBrains Mono, monospace"; ctx.textAlign="center"; ctx.fillText(text,pos.x,pos.y+4);
};

RobotView.prototype._drawRobot = function(ctx,scale,toC) {
    var rp=toC(this.robot.x,this.robot.y), R=Math.max(8,scale*0.25);
    ctx.save(); ctx.shadowColor="#3b82f6"; ctx.shadowBlur=15;
    ctx.fillStyle="rgba(59,130,246,0.3)"; ctx.beginPath(); ctx.arc(rp.x,rp.y,R*1.5,0,Math.PI*2); ctx.fill(); ctx.shadowBlur=0;
    ctx.fillStyle="#3b82f6"; ctx.beginPath(); ctx.arc(rp.x,rp.y,R,0,Math.PI*2); ctx.fill();
    var a=this.robot.angle, ax=rp.x+Math.cos(a)*R*1.6, ay=rp.y-Math.sin(a)*R*1.6;
    var px=-Math.sin(a), py=-Math.cos(a), bx=rp.x+Math.cos(a)*R*0.7, by=rp.y-Math.sin(a)*R*0.7;
    ctx.fillStyle="#fff"; ctx.beginPath(); ctx.moveTo(ax,ay); ctx.lineTo(bx+px*R*0.5,by+py*R*0.5); ctx.lineTo(bx-px*R*0.5,by-py*R*0.5); ctx.closePath(); ctx.fill();
    ctx.fillStyle="#1a1e24"; ctx.beginPath(); ctx.arc(rp.x,rp.y,R*0.3,0,Math.PI*2); ctx.fill(); ctx.restore();
};

RobotView.prototype._drawHUD = function(ctx,w,h,scale) {
    var tc="#64748b";
    ctx.fillStyle=tc; ctx.font="10px JetBrains Mono, monospace"; ctx.textAlign="left";
    ctx.fillText("pos: ("+this.robot.x.toFixed(2)+", "+this.robot.y.toFixed(2)+")", 8, h-24);
    ctx.fillText("hdg: "+(this.robot.angle*180/Math.PI).toFixed(0)+"deg", 8, h-10);
    ctx.textAlign="right"; ctx.fillText("1m", w-8, h-24);
    ctx.strokeStyle=tc; ctx.lineWidth=2; ctx.beginPath(); ctx.moveTo(w-8-scale,h-18); ctx.lineTo(w-8,h-18); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(w-8-scale,h-22); ctx.lineTo(w-8-scale,h-14); ctx.moveTo(w-8,h-22); ctx.lineTo(w-8,h-14); ctx.stroke();
    var compR=16, compX=w-28, compY=28;
    ctx.strokeStyle="#2a3a4e"; ctx.lineWidth=1; ctx.beginPath(); ctx.arc(compX,compY,compR,0,Math.PI*2); ctx.stroke();
    ctx.fillStyle="#ef4444"; ctx.beginPath(); ctx.arc(compX,compY-compR+4,3,0,Math.PI*2); ctx.fill();
    ctx.fillStyle=tc; ctx.font="8px JetBrains Mono"; ctx.textAlign="center"; ctx.fillText("N",compX,compY-compR-4);
    var hx=compX+Math.cos(this.robot.angle)*(compR-5), hy=compY-Math.sin(this.robot.angle)*(compR-5);
    ctx.fillStyle="#3b82f6"; ctx.beginPath(); ctx.arc(hx,hy,2.5,0,Math.PI*2); ctx.fill();
    ctx.fillStyle="rgba(100,116,139,0.5)"; ctx.font="11px JetBrains Mono, monospace"; ctx.textAlign="left";
    ctx.fillText("FACTORY FLOOR - "+this.mapObjects.length+" objects from scene XML", 8, 16);
};

RobotView.prototype._drawLegend = function(ctx,w,h) {
    var y=28, names={wall:"Wall",pillar:"Pillar",shelf:"Shelf",conveyor:"Conveyor",table:"Table",pallet:"Pallet",bollard:"Bollard",box:"Box/Cargo",lane:"Lane",charging_station:"Charging",tool_cabinet:"Cabinet",storage_rack:"Storage",inspection_zone:"Inspect"};
    var cats=["wall","pillar","shelf","conveyor","table","pallet","bollard","box","lane","charging_station","tool_cabinet","storage_rack","inspection_zone"];
    ctx.font="11px JetBrains Mono, monospace"; ctx.textAlign="left";
    for(var i=0;i<cats.length;i++) { var c=cats[i]; if(!this.legendCategories[c]) continue; ctx.fillStyle=this.legendCategories[c]; ctx.beginPath(); ctx.arc(14,y+5,5,0,Math.PI*2); ctx.fill(); ctx.fillStyle="#94a3b8"; ctx.fillText(names[c]||c,26,y+9); y+=18; }
};

RobotView.prototype._drawNavTarget = function(ctx, scale, toC) {
    var t = this.navTarget;
    var tp = toC(t.x, t.y);
    var rp = toC(this.robot.x, this.robot.y);
    var R = Math.max(10, scale * 0.35);
    var time = Date.now() / 1000;
    var pulse = 0.7 + 0.3 * Math.sin(time * 3);

    // Dashed line from robot to target
    ctx.save();
    ctx.strokeStyle = "rgba(168, 85, 247, 0.35)";
    ctx.lineWidth = 2;
    ctx.setLineDash([scale * 0.15, scale * 0.1]);
    ctx.beginPath();
    ctx.moveTo(rp.x, rp.y);
    ctx.lineTo(tp.x, tp.y);
    ctx.stroke();
    ctx.setLineDash([]);

    // Pulsing target ring
    ctx.strokeStyle = "rgba(168, 85, 247, " + (pulse * 0.6) + ")";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(tp.x, tp.y, R * pulse, 0, Math.PI * 2);
    ctx.stroke();

    // Inner dot
    ctx.fillStyle = "rgba(168, 85, 247, 0.7)";
    ctx.beginPath();
    ctx.arc(tp.x, tp.y, 4, 0, Math.PI * 2);
    ctx.fill();

    // Crosshair
    ctx.strokeStyle = "rgba(168, 85, 247, 0.4)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(tp.x - R, tp.y); ctx.lineTo(tp.x + R, tp.y);
    ctx.moveTo(tp.x, tp.y - R); ctx.lineTo(tp.x, tp.y + R);
    ctx.stroke();

    // Label
    ctx.fillStyle = "#a855f7";
    ctx.font = Math.max(10, scale * 0.25) + "px JetBrains Mono, monospace";
    ctx.textAlign = "center";
    ctx.fillText(t.name || "TARGET", tp.x, tp.y - R - 6);

    ctx.restore();
};

RobotView.prototype._drawMultiRobot = function(ctx, scale, toC, robotData) {
    var pos = robotData.position || [0,0,0];
    var rp = toC(pos[0], pos[1]);
    var R = Math.max(8, scale * 0.25);
    var color = robotData.color || "#3b82f6";
    var isSelected = robotData.selected;
    var angle = robotData.orientation || 0;

    ctx.save();

    // Pulsing selection ring for selected robot
    if (isSelected) {
        var time = Date.now() / 1000;
        var pulse = 0.6 + 0.4 * Math.sin(time * 4);
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.globalAlpha = pulse;
        ctx.beginPath();
        ctx.arc(rp.x, rp.y, R * 1.8, 0, Math.PI * 2);
        ctx.stroke();
        ctx.globalAlpha = 1;
        ctx.shadowColor = color;
        ctx.shadowBlur = 15;
    }

    // Glow
    var c = this._hex2rgb(color);
    ctx.fillStyle = "rgba(" + c.r + "," + c.g + "," + c.b + ",0.3)";
    ctx.beginPath(); ctx.arc(rp.x, rp.y, R * 1.5, 0, Math.PI * 2); ctx.fill();
    ctx.shadowBlur = 0;

    // Body
    ctx.fillStyle = color;
    ctx.beginPath(); ctx.arc(rp.x, rp.y, R, 0, Math.PI * 2); ctx.fill();

    // Direction arrow
    var ax = rp.x + Math.cos(angle) * R * 1.6, ay = rp.y - Math.sin(angle) * R * 1.6;
    var px = -Math.sin(angle), py = -Math.cos(angle);
    var bx = rp.x + Math.cos(angle) * R * 0.7, by = rp.y - Math.sin(angle) * R * 0.7;
    ctx.fillStyle = "#fff";
    ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx + px * R * 0.5, by + py * R * 0.5); ctx.lineTo(bx - px * R * 0.5, by - py * R * 0.5); ctx.closePath(); ctx.fill();

    // Center dot
    ctx.fillStyle = "#1a1e24";
    ctx.beginPath(); ctx.arc(rp.x, rp.y, R * 0.3, 0, Math.PI * 2); ctx.fill();

    // ID label below
    ctx.fillStyle = color;
    ctx.font = Math.max(8, scale * 0.18) + "px JetBrains Mono, monospace";
    ctx.textAlign = "center";
    ctx.fillText(robotData.id.replace("robot_", "R"), rp.x, rp.y + R + Math.max(10, scale * 0.3));

    ctx.restore();
};

RobotView.prototype._handleClick = function(e) {
    if (!this.allRobots || this.allRobots.length === 0 || !this.onRobotClick) return;
    var rect = this.canvas.getBoundingClientRect();
    var cx = this.canvas.width / 2, cy = this.canvas.height / 2;
    var scale = Math.min(this.canvas.width, this.canvas.height) / (this.viewRange * 2);
    var clickX = e.clientX - rect.left;
    var clickY = e.clientY - rect.top;
    var hitRadius = Math.max(15, scale * 0.4);

    for (var i = 0; i < this.allRobots.length; i++) {
        var r = this.allRobots[i];
        var pos = r.position || [0, 0, 0];
        var sp = this._toC(pos[0], pos[1], scale, cx, cy);
        var dx = clickX - sp.x, dy = clickY - sp.y;
        if (dx * dx + dy * dy < hitRadius * hitRadius) {
            this.onRobotClick(r.id);
            return;
        }
    }
};

RobotView.prototype._lighten = function(hex,a) { var c=this._hex2rgb(hex); return "rgb("+Math.min(255,c.r+a*255)+","+Math.min(255,c.g+a*255)+","+Math.min(255,c.b+a*255)+")"; };
RobotView.prototype._darken = function(hex,a) { var c=this._hex2rgb(hex); return "rgb("+Math.max(0,c.r-a*255)+","+Math.max(0,c.g-a*255)+","+Math.max(0,c.b-a*255)+")"; };
RobotView.prototype._hex2rgb = function(hex) { var m=/^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex); return m?{r:parseInt(m[1],16),g:parseInt(m[2],16),b:parseInt(m[3],16)}:{r:128,g:128,b:128}; };
