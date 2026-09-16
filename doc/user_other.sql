/*
 Navicat Premium Dump SQL

 Source Server         : ush-dev
 Source Server Type    : MySQL
 Source Server Version : 80031 (8.0.31)
 Source Host           : 127.0.0.1:3306
 Source Schema         : ush_dev

 Target Server Type    : MySQL
 Target Server Version : 80031 (8.0.31)
 File Encoding         : 65001

 Date: 15/09/2026 17:48:08
*/

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ----------------------------
-- Table structure for user_other
-- ----------------------------
DROP TABLE IF EXISTS `user_other`;
CREATE TABLE `user_other`  (
  `user_id` int NOT NULL,
  `system_mail` varchar(4000) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '领取系统邮件id列表',
  `phone_model` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT '' COMMENT '机型',
  `phone_os_version` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT '' COMMENT '系统版本号',
  `app_version` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT '' COMMENT 'app版本号',
  `created_at` int NOT NULL DEFAULT 0,
  `sc_token` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL DEFAULT '',
  `gc_token` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL DEFAULT '',
  `online_time_total` bigint UNSIGNED NOT NULL DEFAULT 0 COMMENT '总在线时长',
  `online_time` int UNSIGNED NOT NULL DEFAULT 0 COMMENT '当日在线时长',
  `online_time_last_updated_at` int UNSIGNED NOT NULL DEFAULT 0 COMMENT '在线时长最后修改时间',
  `last_login_date` char(8) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL DEFAULT '' COMMENT '最后登录日期',
  `login_day_total` int UNSIGNED NOT NULL DEFAULT 0 COMMENT '累计登录天数',
  `bet_total` bigint UNSIGNED NOT NULL DEFAULT 0 COMMENT '下注总额',
  `bet_times` int NULL DEFAULT 0 COMMENT '下注次数',
  `win_sc_times` int UNSIGNED NOT NULL DEFAULT 0 COMMENT '赢取sc总次数',
  `win_sc_total` int UNSIGNED NOT NULL DEFAULT 0 COMMENT '赢取SC总额(单位:美分)',
  `bet_exp_gc` bigint UNSIGNED NOT NULL DEFAULT 0 COMMENT '投注gc兑换经验池子',
  `bet_exp_sc` bigint UNSIGNED NOT NULL DEFAULT 0 COMMENT '投注sc兑换经验池子',
  `adjust_param` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL COMMENT 'adjust参数,前端控制',
  `adjust_info` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL COMMENT 'adjust初始参数',
  `authorization_info` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL COMMENT '撤出用户绑定信息',
  `is_get_guide_reward` tinyint(1) NOT NULL DEFAULT 0 COMMENT '是否已领取引导奖励 0 否 1 是',
  `is_comment_reward` tinyint(1) NULL DEFAULT 0 COMMENT '是否领取评论奖励 0 否 1是',
  `gpsid` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL DEFAULT '' COMMENT 'gpsid',
  `jackpot_score` int UNSIGNED NOT NULL DEFAULT 0 COMMENT 'jackpot代币数量',
  `recharge_rebate_score` int UNSIGNED NOT NULL DEFAULT 0 COMMENT '充值返利代币数量',
  `activity_reddot` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT '' COMMENT '活动红点列表：',
  `activity_reddot_reward` tinyint(1) NOT NULL DEFAULT 0 COMMENT '活动红点奖励',
  `bust_ad_num` int NULL DEFAULT 0 COMMENT '破产广告次数',
  `bust_ad_gc` int NULL DEFAULT NULL COMMENT '破产广告礼包gc',
  `epay_bank_wallet` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT '' COMMENT 'epaybank钱包',
  `epay_usdt_wallet` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT '' COMMENT 'epayusdt钱包',
  `waipay_wallet` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT '' COMMENT 'waipay钱包',
  `cloudmod_wallet` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT '' COMMENT 'cloudmod钱包',
  `jumio_account_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT 'jumio账号Id',
  `jumio_verified_info` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT 'jumio验证信息',
  `return_type` tinyint(1) NULL DEFAULT 0 COMMENT '1 pay 2super pay',
  `return_send_time` int NULL DEFAULT 0 COMMENT '回归发送时间',
  `lucky_spin_last_time` int NULL DEFAULT NULL COMMENT '最后参与的luckyspin活动开始时间',
  `avatar_list` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '获得的特殊头像列表',
  `avatar_frame_list` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '获得的特殊头像框列表',
  `act_score_compensation` tinyint(1) NULL DEFAULT 0 COMMENT '活动积分补偿(1:已补偿)',
  `three_day_reward_info` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '新人三日奖励数据(最后一次领取天数:最后一次领取时间)',
  `today_bust_info` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '今日破产信息',
  `last_piggy_dividend_time` int NULL DEFAULT NULL COMMENT '最后触发金猪分红时间',
  `pay_list` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT '' COMMENT '充值渠道列表：  渠道,封禁时间戳|渠道,封禁时间戳',
  `coupon_expire_flag` tinyint(1) NULL DEFAULT NULL COMMENT '优惠券过期处理标志(1:已处理)',
  `max_sc_win_rate` decimal(10, 2) UNSIGNED NOT NULL DEFAULT 0.00 COMMENT '投注SC最大赢取倍率',
  `first_charge_reward_status` tinyint(1) NULL DEFAULT NULL COMMENT '首充额外奖励状态(1:已首充未领取 2:已领取)',
  `order_times` int UNSIGNED NOT NULL DEFAULT 0 COMMENT '下单总数(包含已支付和未支付)',
  `turnover_updated_time` int UNSIGNED NOT NULL DEFAULT 0 COMMENT '周转率更新时间',
  `turnover_analysis_time` int UNSIGNED NOT NULL DEFAULT 0 COMMENT '周转率分析时间',
  `turnover_bet_total` int UNSIGNED NOT NULL DEFAULT 0 COMMENT '周转率投注总额(双周)',
  `turnover_charge_total` int UNSIGNED NOT NULL DEFAULT 0 COMMENT '周转率充值总额(双周)',
  `daily_wheel_count` int NOT NULL DEFAULT 0 COMMENT '每日转盘次数',
  `daily_wheel_daily_count` int NOT NULL COMMENT '每日转盘每日次数',
  `daily_wheel_last_time` int NOT NULL DEFAULT 0 COMMENT '最后转动转盘时间',
  `table_game_black_status` tinyint NOT NULL DEFAULT 0 COMMENT 'tg黑名单状态(0-非黑名单 1-主动移入黑名单 2-人工移入黑名单 3-人工移出黑名单 )',
  `table_game_black_time` int NOT NULL DEFAULT 0 COMMENT '黑名单检测时间',
  `table_game_bet_total` int NOT NULL DEFAULT -1 COMMENT 'tablegame下注总额',
  `notice_reward_count` int NOT NULL DEFAULT 0 COMMENT '领取推送奖励次数',
  `notice_reward_last_time` int UNSIGNED NOT NULL DEFAULT 0 COMMENT '最后领取推送奖励时间',
  `turnover_black_status` tinyint NOT NULL DEFAULT 0 COMMENT 'tu黑名单状态(0-非黑名单 1-主动移入黑名单)',
  `turnover_history_charge_total` int UNSIGNED NOT NULL DEFAULT 0 COMMENT '周转率充值总额(终身)',
  `turnover_history_bet_total` int UNSIGNED NOT NULL DEFAULT 0 COMMENT '周转率投注总额(终身)',
  `daily_wheel_level` int UNSIGNED NOT NULL DEFAULT 1 COMMENT '每日转轮等级',
  `vip_reward_list` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '已购买过的VIP礼包',
  `daily_wheel_add_exp_time` int NULL DEFAULT 0,
  `daily_wheel_exp` int NULL DEFAULT 0,
  `first_cashout_order_sn` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT '' COMMENT '新手首撤礼包订单',
  `first_cashout_state` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT 'none' COMMENT '新手首撤礼包状态',
  `jackpot_ticket` int NULL DEFAULT 0 COMMENT 'jackpot抽奖券',
  `jackpot_bet_score` int NULL DEFAULT 0 COMMENT 'jackpot当前下注积分',
  `mail_last_processed_time` int NULL DEFAULT 0 COMMENT '邮件最后处理时间',
  `newbie_gifts_status` bigint NULL DEFAULT 0 COMMENT '新手礼包状态信息',
  `real_name_status` tinyint(1) NULL DEFAULT 0 COMMENT '合规实名状态',
  `biweekly_srtp_update_time` int NULL DEFAULT 0 COMMENT '双周SRTP更新时间',
  `biweekly_bet_sc` int NULL DEFAULT 0 COMMENT '双周下注总额',
  `biweekly_win_sc` int NULL DEFAULT 0 COMMENT '双周赢注总额',
  `vip_lv_rewards` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT '' COMMENT '已领取的VIP奖励 1|2|3',
  `enabled_tradpay` tinyint(1) NULL DEFAULT 0 COMMENT '1:启用tradpay',
  `treasure_box_reward_daily_count` int NULL DEFAULT 0 COMMENT '百宝箱每日奖励次数',
  `treasure_box_reward_last_time` int NULL DEFAULT 0 COMMENT '百宝箱最后领奖时间',
  PRIMARY KEY (`user_id`) USING BTREE,
  UNIQUE INDEX `user_id`(`user_id` ASC) USING BTREE,
  UNIQUE INDEX `sc_token`(`sc_token` ASC) USING BTREE,
  UNIQUE INDEX `gc_token`(`gc_token` ASC) USING BTREE,
  INDEX `jumio_account_id`(`jumio_account_id` ASC) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '用户信息表' ROW_FORMAT = DYNAMIC;

SET FOREIGN_KEY_CHECKS = 1;
