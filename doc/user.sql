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

 Date: 15/09/2026 17:47:02
*/

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ----------------------------
-- Table structure for user
-- ----------------------------
DROP TABLE IF EXISTS `user`;
CREATE TABLE `user`  (
  `id` int UNSIGNED NOT NULL AUTO_INCREMENT,
  `avatar` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '头像',
  `avatar_frame` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT '' COMMENT '头像框',
  `username` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '用户名',
  `nickname` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '昵称',
  `password` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '密码',
  `oaid` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT 'oaid',
  `adid` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT '' COMMENT 'adid',
  `money` bigint UNSIGNED NOT NULL DEFAULT 0 COMMENT '余额(单位：分)',
  `gc` bigint UNSIGNED NOT NULL DEFAULT 0 COMMENT '金币',
  `bonus` bigint UNSIGNED NOT NULL DEFAULT 0 COMMENT 'bonus',
  `email` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL DEFAULT '' COMMENT '邮箱',
  `type` tinyint(1) NULL DEFAULT 0 COMMENT '账号类型 0 游客 1 注册用户',
  `vip_level` int UNSIGNED NULL DEFAULT 0 COMMENT 'vip等级',
  `vip_exp` bigint UNSIGNED NULL DEFAULT 0 COMMENT 'vip经验',
  `is_vip_friend` tinyint(1) NOT NULL DEFAULT 0 COMMENT '是否vip客服好友',
  `level` int UNSIGNED NULL DEFAULT 0 COMMENT '等级',
  `exp` bigint UNSIGNED NULL DEFAULT 0 COMMENT '经验',
  `charge_total` int UNSIGNED NOT NULL DEFAULT 0 COMMENT '累充总额度(单位：分)',
  `charge_times` int UNSIGNED NOT NULL DEFAULT 0 COMMENT '累充总次数',
  `withdraw_total` int UNSIGNED NOT NULL DEFAULT 0 COMMENT '累计撤回总额度(单位：分)',
  `withdraw_times` int UNSIGNED NOT NULL DEFAULT 0 COMMENT '累计撤回总次数',
  `withdraw_fee` int NULL DEFAULT NULL COMMENT '累计撤回手续费',
  `last_login_at` int UNSIGNED NOT NULL DEFAULT 0 COMMENT '最后一次登录时间',
  `last_login_ip` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT '' COMMENT '最后一次登录ip',
  `register_ip` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '创建ip',
  `is_test` tinyint UNSIGNED NULL DEFAULT 0 COMMENT '是否测试用户 0 否 1 是',
  `is_risk` tinyint(1) NULL DEFAULT 0 COMMENT '是否风险用户 0 否 1 是',
  `platform` tinyint(1) NULL DEFAULT NULL COMMENT '注册平台 平台 0 通用 1 web 2 安卓 3ios',
  `pkg_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL DEFAULT '' COMMENT '注册包名',
  `wallet` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '钱包',
  `cash_wallet` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT 'cash钱包',
  `epay_wallet` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT '' COMMENT 'epay钱包',
  `channel_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL DEFAULT '' COMMENT '注册渠道=adjust.network',
  `creative` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '注册creative',
  `campaign` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '注册campaign',
  `distribution_channel` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL DEFAULT '' COMMENT '分发渠道',
  `country` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL DEFAULT '' COMMENT '国家',
  `province` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL DEFAULT '' COMMENT '省份',
  `user_agent` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT '' COMMENT 'user_agent',
  `created_at` int UNSIGNED NOT NULL DEFAULT 0 COMMENT '创建时间',
  `updated_at` int UNSIGNED NOT NULL DEFAULT 0 COMMENT '修改时间',
  `deleted_at` int UNSIGNED NULL DEFAULT 0 COMMENT '删除时间',
  `status` tinyint(1) NULL DEFAULT NULL COMMENT '状态 0 禁用 1 正常',
  `pay_status` tinyint(1) NOT NULL DEFAULT 1 COMMENT '充值撤出状态：0 禁用 1 正常',
  `is_echeck_late` tinyint(1) NOT NULL DEFAULT 0 COMMENT '是否echeck延迟用户  0 否 1 是',
  `is_frozen` tinyint(1) NULL DEFAULT 0 COMMENT '是否冻结订单用户 0 否1是',
  `is_credit_card` tinyint(1) NULL DEFAULT 0 COMMENT '是否是信用卡用户 0 否1是',
  `installed_at` int NULL DEFAULT 0 COMMENT '首次安装时间',
  `update_date` datetime NULL DEFAULT NULL COMMENT '更新时间',
  `dispute_status` tinyint NULL DEFAULT 0 COMMENT '争议黑名单状态',
  `is_paypal` tinyint(1) NULL DEFAULT 0 COMMENT '是否是PayPal 0否1是',
  `compliance_status` tinyint(1) NULL DEFAULT 0 COMMENT '是否是合规用户 1是',
  `in_handling_disputes` tinyint(1) NULL DEFAULT 0 COMMENT '是否在处理争议中',
  `raw_afid` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT '',
  `raw_adid` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT '',
  `apple_user_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '苹果用户Id',
  `is_private_email` tinyint(1) NULL DEFAULT 0 COMMENT '是否代理邮箱(1:是) 苹果用户才有代理邮箱',
  `advertising_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '',
  `login_distribution_channel` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT '' COMMENT '登录渠道',
  `bi_update_time` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT 'BI 更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `username`(`username` ASC, `distribution_channel` ASC, `platform` ASC) USING BTREE,
  INDEX `oaid`(`oaid` ASC) USING BTREE,
  INDEX `adid`(`adid` ASC) USING BTREE,
  INDEX `email`(`email` ASC) USING BTREE,
  INDEX `created_at`(`created_at` ASC) USING BTREE,
  INDEX `vip_level`(`vip_level` ASC) USING BTREE,
  INDEX `advertising_idx`(`advertising_id` ASC) USING BTREE,
  INDEX `raw_afid`(`raw_afid` ASC) USING BTREE,
  INDEX `idx_bi_update_time`(`bi_update_time` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 576069 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci COMMENT = '用户表' ROW_FORMAT = Dynamic;

SET FOREIGN_KEY_CHECKS = 1;
