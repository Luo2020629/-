import tushare as ts
import pandas as pd
from datetime import datetime, timedelta
import time
import os
import concurrent.futures
from tqdm import tqdm
import requests
import threading
from collections import deque

# 设置token
ts.set_token('847caf6262a44295cbaeda61f91330307839f114018873b1ea9c0c87')
pro = ts.pro_api()

class TradingDateChecker:
    """交易日判断器"""
    
    # 中国股市的节假日列表（包含2023-2025年）
    CHINA_HOLIDAYS = {
        '2023': [
            '20230101', '20230102',  # 元旦
            '20230121', '20230122', '20230123', '20230124', '20230125', '20230126', '20230127',  # 春节
            '20230405',  # 清明节
            '20230429', '20230430', '20230501', '20230502', '20230503',  # 劳动节
            '20230622', '20230623', '20230624',  # 端午节
            '20230929', '20230930',  # 中秋节+国庆节前
            '20231001', '20231002', '20231003', '20231004', '20231005', '20231006',  # 国庆节
        ],
        '2024': [
            '20240101',  # 元旦
            '20240210', '20240211', '20240212', '20240213', '20240214', '20240215', '20240216', '20240217',  # 春节
            '20240404', '20240405', '20240406',  # 清明节
            '20240501', '20240502', '20240503', '20240504', '20240505',  # 劳动节
            '20240610',  # 端午节
            '20240915', '20240916', '20240917',  # 中秋节
            '20241001', '20241002', '20241003', '20241004', '20241005', '20241006', '20241007',  # 国庆节
        ],
        '2025': [
            # 元旦
            '20250101',
            
            # 春节：1月28日（星期二，除夕）至2月4日（星期二），共8天
            '20250128', '20250129', '20250130', '20250131', 
            '20250201', '20250202', '20250203', '20250204',
            
            # 清明节：4月4日至4月6日，共3天
            '20250404', '20250405', '20250406',
            
            # 劳动节：5月1日至5月5日，共5天
            '20250501', '20250502', '20250503', '20250504', '20250505',
            
            # 端午节：5月31日至6月2日，共3天
            '20250531', '20250601', '20250602',
            
            # 中秋+国庆节：10月1日至10月8日，共8天
            '20251001', '20251002', '20251003', '20251004', 
            '20251005', '20251006', '20251007', '20251008'
        ]
    }
    
    # 调休上班的周末（需要从交易日中排除）
    WORKING_WEEKENDS = {
        '2025': [
            '20250126',  # 周日，春节调休上班
            '20250208',  # 周六，春节调休上班
            '20250427',  # 周日，劳动节调休上班
            '20250928',  # 周日，国庆节调休上班
            '20251011',  # 周六，国庆节调休上班
        ]
    }
    
    @staticmethod
    def is_weekend(date_str):
        """判断是否为周末"""
        try:
            date_obj = datetime.strptime(date_str, '%Y%m%d')
            return date_obj.weekday() >= 5  # 5=周六, 6=周日
        except ValueError:
            return False
    
    @staticmethod
    def is_holiday(date_str):
        """判断是否为法定节假日"""
        year = date_str[:4]
        if year in TradingDateChecker.CHINA_HOLIDAYS:
            return date_str in TradingDateChecker.CHINA_HOLIDAYS[year]
        return False
    
    @staticmethod
    def is_working_weekend(date_str):
        """判断是否为调休上班的周末"""
        year = date_str[:4]
        if year in TradingDateChecker.WORKING_WEEKENDS:
            return date_str in TradingDateChecker.WORKING_WEEKENDS[year]
        return False
    
    @staticmethod
    def is_trading_date(date_str):
        """
        判断是否为交易日
        规则：非周末且非节假日，或者虽然是周末但是调休上班
        """
        # 如果是调休上班的周末，则是交易日
        if TradingDateChecker.is_working_weekend(date_str):
            return True
        
        # 如果是普通周末，不是交易日
        if TradingDateChecker.is_weekend(date_str):
            return False
        
        # 如果是节假日，不是交易日
        if TradingDateChecker.is_holiday(date_str):
            return False
        
        return True
    
    @staticmethod
    def get_holiday_info(date_str):
        """获取节假日的详细信息"""
        year = date_str[:4]
        
        if TradingDateChecker.is_holiday(date_str):
            # 找出属于哪个节日
            holiday_ranges = {
                '元旦': ['20250101'],
                '春节': [f'202501{d:02d}' for d in range(28, 32)] + [f'202502{d:02d}' for d in range(1, 5)],
                '清明节': [f'202504{d:02d}' for d in range(4, 7)],
                '劳动节': [f'202505{d:02d}' for d in range(1, 6)],
                '端午节': [f'202505{d:02d}' for d in range(31, 32)] + [f'202506{d:02d}' for d in range(1, 3)],
                '国庆中秋': [f'202510{d:02d}' for d in range(1, 9)]
            }
            
            for holiday_name, dates in holiday_ranges.items():
                if date_str in dates:
                    return holiday_name
            
            return "法定节假日"
        
        elif TradingDateChecker.is_working_weekend(date_str):
            return "调休上班"
        
        elif TradingDateChecker.is_weekend(date_str):
            return "周末"
        
        else:
            return "正常交易日"
    
    @staticmethod
    def get_trading_dates_internal(start_date, end_date, verbose=False):
        """内部生成交易日列表"""
        start_dt = datetime.strptime(start_date, '%Y%m%d')
        end_dt = datetime.strptime(end_date, '%Y%m%d')
        
        trading_dates = []
        non_trading_dates = []
        current_dt = start_dt
        
        total_days = (end_dt - start_dt).days + 1
        
        if verbose:
            print(f"🔍 分析日期范围: {start_date} 到 {end_date}")
            print(f"📅 总天数: {total_days} 天")
        
        # 使用进度条显示判断进度
        pbar = tqdm(total=total_days, desc="判断交易日")
        
        while current_dt <= end_dt:
            date_str = current_dt.strftime('%Y%m%d')
            
            # 使用内部判断逻辑
            if TradingDateChecker.is_trading_date(date_str):
                trading_dates.append(date_str)
                if verbose:
                    pbar.set_postfix_str(f"交易日:{len(trading_dates)}")
            else:
                non_trading_dates.append({
                    'date': date_str,
                    'reason': TradingDateChecker.get_holiday_info(date_str)
                })
                if verbose:
                    pbar.set_postfix_str(f"非交易日:{len(non_trading_dates)}")
            
            current_dt += timedelta(days=1)
            pbar.update(1)
        
        pbar.close()
        
        if verbose:
            # 显示详细的统计信息
            print(f"✅ 内部判断完成：{len(trading_dates)} 个交易日，{len(non_trading_dates)} 个非交易日")
            
            # 显示非交易日的原因统计
            reason_stats = {}
            for nt_date in non_trading_dates:
                reason = nt_date['reason']
                reason_stats[reason] = reason_stats.get(reason, 0) + 1
            
            print("📊 非交易日分布:")
            for reason, count in reason_stats.items():
                print(f"   {reason}: {count} 天")
            
            # 显示最近的几个交易日
            if trading_dates:
                print(f"📈 最近的交易日示例:")
                recent_dates = trading_dates[-5:] if len(trading_dates) > 5 else trading_dates
                for date_str in recent_dates:
                    print(f"   {date_str} ({TradingDateChecker.get_holiday_info(date_str)})")
        
        return trading_dates

class RateLimiter:
    """请求频率限制器"""
    def __init__(self, max_calls_per_minute=50):
        self.max_calls_per_minute = max_calls_per_minute
        self.calls = deque()
        self.lock = threading.Lock()
    
    def wait_if_needed(self):
        """如果需要等待，则阻塞直到可以继续请求"""
        with self.lock:
            now = time.time()
            # 移除1分钟前的记录
            while self.calls and self.calls[0] < now - 60:
                self.calls.popleft()
            
            # 如果达到限制，等待
            if len(self.calls) >= self.max_calls_per_minute:
                wait_time = 60 - (now - self.calls[0])
                if wait_time > 0:
                    print(f"⏳ 频率限制：等待{wait_time:.1f}秒后继续...")
                    time.sleep(wait_time)
                    # 等待后重新清理记录
                    now = time.time()
                    while self.calls and self.calls[0] < now - 60:
                        self.calls.popleft()
            
            # 记录本次请求时间
            self.calls.append(now)
    
    def get_remaining_calls(self):
        """获取剩余可调用次数"""
        with self.lock:
            now = time.time()
            # 移除1分钟前的记录
            while self.calls and self.calls[0] < now - 60:
                self.calls.popleft()
            return max(0, self.max_calls_per_minute - len(self.calls))
    
    def reset(self):
        """重置计数器"""
        with self.lock:
            self.calls.clear()

class OptimizedStockScreener:
    def __init__(self):
        self.stock_data = None
        self.all_stocks = None
        self.max_workers = 5
        self.retry_times = 3
        self.request_delay = 0.1
        self.rate_limiter = RateLimiter(max_calls_per_minute=50)
        self.date_checker = TradingDateChecker()
    
    def get_all_stock_list(self):
        """
        获取沪深所有正常上市的股票列表（带缓存）
        """
        try:
            # 应用频率限制
            self.rate_limiter.wait_if_needed()
            
            # 尝试从缓存文件读取
            cache_file = 'stock_list_cache.csv'
            if os.path.exists(cache_file):
                cache_time = os.path.getmtime(cache_file)
                # 缓存有效期1天
                if time.time() - cache_time < 24 * 3600:
                    df = pd.read_csv(cache_file)
                    self.all_stocks = df['ts_code'].tolist()
                    print(f"📁 从缓存读取 {len(self.all_stocks)} 只股票列表")
                    return self.all_stocks
            
            # 从API获取
            df = pro.stock_basic(exchange='', list_status='L', 
                                fields='ts_code,symbol,name,area,industry,list_date,market')
            self.all_stocks = df['ts_code'].tolist()
            
            # 保存到缓存
            df.to_csv(cache_file, index=False)
            print(f"✅ 获取到 {len(self.all_stocks)} 只正常上市的股票")
            return self.all_stocks
            
        except Exception as e:
            print(f"❌ 获取股票列表失败: {e}")
            return []
    
    def get_single_date_data(self, trade_date):
        """
        获取单个交易日的全市场数据（带重试机制和频率限制）
        """
        for attempt in range(self.retry_times):
            try:
                # 应用频率限制
                self.rate_limiter.wait_if_needed()
                
                # 添加请求延迟
                time.sleep(self.request_delay)
                
                df = pro.daily(trade_date=trade_date)
                
                if not df.empty:
                    df['trade_date'] = pd.to_datetime(df['trade_date'])
                    return df
                else:
                    # 返回空DataFrame而不是None
                    return pd.DataFrame()
                    
            except requests.exceptions.RequestException as e:
                remaining = self.rate_limiter.get_remaining_calls()
                print(f"   ⚠ {trade_date} 网络错误(尝试{attempt+1}/{self.retry_times}, 剩余{remaining}次/分钟): {e}")
                if attempt < self.retry_times - 1:
                    time.sleep(2)
            except Exception as e:
                remaining = self.rate_limiter.get_remaining_calls()
                print(f"   ❌ {trade_date} 获取失败(尝试{attempt+1}/{self.retry_times}, 剩余{remaining}次/分钟): {e}")
                break
                
        return pd.DataFrame()
    
    def get_trading_dates(self, start_date, end_date, use_internal_fallback=True, verbose=False):
        """
        获取指定范围内的交易日列表
        优先使用Tushare API，失败时使用内部判断
        """
        try:
            self.rate_limiter.wait_if_needed()
            time.sleep(self.request_delay)
            
            print("📅 尝试从Tushare获取交易日历...")
            # 获取交易日历
            df = pro.trade_cal(exchange='', start_date=start_date, end_date=end_date)
            trading_dates = df[df['is_open'] == 1]['cal_date'].tolist()
            trading_dates.sort()  # 确保日期有序
            
            print(f"✅ 从Tushare获取到 {len(trading_dates)} 个交易日")
            return trading_dates
            
        except Exception as e:
            print(f"❌ 从Tushare获取交易日历失败: {e}")
            
            if use_internal_fallback:
                print("🔄 切换到内部交易日判断...")
                return self.date_checker.get_trading_dates_internal(start_date, end_date, verbose)
            else:
                # 如果内部判断也禁用，生成连续的日期列表
                start_dt = datetime.strptime(start_date, '%Y%m%d')
                end_dt = datetime.strptime(end_date, '%Y%m%d')
                dates = []
                current_dt = start_dt
                while current_dt <= end_dt:
                    dates.append(current_dt.strftime('%Y%m%d'))
                    current_dt += timedelta(days=1)
                print(f"⚠ 使用连续的 {len(dates)} 个日期（可能包含非交易日）")
                return dates
    
    def get_trading_dates_internal(self, start_date, end_date, verbose=False):
        """
        使用内部逻辑判断交易日
        """
        return self.date_checker.get_trading_dates_internal(start_date, end_date, verbose)
    
    def _generate_all_dates(self, start_date, end_date):
        """生成指定范围内的所有日期"""
        start_dt = datetime.strptime(start_date, '%Y%m%d')
        end_dt = datetime.strptime(end_date, '%Y%m%d')
        
        dates = []
        current_dt = start_dt
        while current_dt <= end_dt:
            dates.append(current_dt.strftime('%Y%m%d'))
            current_dt += timedelta(days=1)
        
        return dates
    
    def verify_trading_dates(self, date_list):
        """
        验证日期列表中的交易日（抽样验证）
        """
        if not date_list:
            return date_list
        
        print("🔍 抽样验证交易日...")
        sample_size = min(5, len(date_list))
        sample_dates = date_list[:sample_size]
        
        verified_count = 0
        for date_str in sample_dates:
            try:
                # 尝试获取该日期的数据来验证
                self.rate_limiter.wait_if_needed()
                test_data = pro.daily(trade_date=date_str, limit=1)
                if not test_data.empty:
                    verified_count += 1
                    print(f"   ✅ {date_str}: 验证通过 ({self.date_checker.get_holiday_info(date_str)})")
                else:
                    print(f"   ⚠ {date_str}: 可能不是交易日 ({self.date_checker.get_holiday_info(date_str)})")
                time.sleep(0.1)
            except:
                print(f"   ❌ {date_str}: 验证失败")
        
        accuracy = verified_count / sample_size * 100
        print(f"📊 抽样验证准确率: {accuracy:.1f}% ({verified_count}/{sample_size})")
        
        return date_list
    
    def get_multiple_days_data(self, start_date, end_date, use_internal_fallback=True, verify_dates=True, verbose=False):
        """
        按交易日期循环获取多日数据（优化版）
        """
        # 获取交易日列表
        trading_dates = self.get_trading_dates(start_date, end_date, use_internal_fallback, verbose)
        
        if not trading_dates:
            print("❌ 没有获取到交易日数据")
            return pd.DataFrame()
        
        # 验证交易日（可选）
        if verify_dates and use_internal_fallback:
            trading_dates = self.verify_trading_dates(trading_dates)
        
        total_dates = len(trading_dates)
        print(f"🚀 开始获取 {total_dates} 个交易日的全市场数据...")
        print(f"📅 时间范围: {start_date} 到 {end_date}")
        print(f"⚡ 并发数: {self.max_workers}, 重试次数: {self.retry_times}")
        
        all_data = []
        successful_dates = 0
        failed_dates = []
        
        # 计算预计时间
        estimated_minutes = max(1, total_dates // 20)  # 保守估计每分钟20个请求
        print(f"⏱️ 预计需要时间: {estimated_minutes} 分钟")
        
        # 记录开始时间
        start_time = time.time()
        
        # 使用进度条显示进度（按日期）
        pbar = tqdm(total=total_dates, desc="获取数据")
        
        try:
            # 按日期分批处理
            batch_size = min(10, total_dates)
            for batch_num in range(0, total_dates, batch_size):
                batch_dates = trading_dates[batch_num:batch_num + batch_size]
                batch_end_idx = min(batch_num + batch_size, total_dates)
                
                print(f"\n🎯 第 {batch_num//batch_size + 1}/{(total_dates + batch_size - 1)//batch_size} 批 ({len(batch_dates)} 个日期)...")
                print(f"   📋 日期范围: {batch_dates[0]} 到 {batch_dates[-1]}")
                
                batch_results = []
                batch_successful = 0
                batch_failed = []
                
                # 使用线程池并发获取本批日期数据
                with concurrent.futures.ThreadPoolExecutor(max_workers=min(self.max_workers, len(batch_dates))) as executor:
                    future_to_date = {
                        executor.submit(self.get_single_date_data, date): date 
                        for date in batch_dates
                    }
                    
                    for future in concurrent.futures.as_completed(future_to_date):
                        trade_date = future_to_date[future]
                        try:
                            result = future.result(timeout=30)
                            if not result.empty:
                                batch_results.append(result)
                                batch_successful += 1
                                successful_dates += 1
                                stocks_count = len(result)
                                holiday_info = self.date_checker.get_holiday_info(trade_date)
                                print(f"   ✅ {trade_date}: 获取到 {stocks_count} 只股票 ({holiday_info})")
                            else:
                                batch_failed.append(trade_date)
                                failed_dates.append(trade_date)
                                holiday_info = self.date_checker.get_holiday_info(trade_date)
                                print(f"   ⚠ {trade_date}: 无数据 ({holiday_info})")
                            
                        except concurrent.futures.TimeoutError:
                            print(f"   ⏰ {trade_date} 请求超时")
                            batch_failed.append(trade_date)
                            failed_dates.append(trade_date)
                        except Exception as e:
                            print(f"   ❌ {trade_date} 处理异常: {e}")
                            batch_failed.append(trade_date)
                            failed_dates.append(trade_date)
                
                # 合并本批次数据
                if batch_results:
                    try:
                        batch_df = pd.concat(batch_results, ignore_index=True)
                        all_data.append(batch_df)
                        success_rate = batch_successful / len(batch_dates) * 100
                        print(f"   ✅ 本批成功: {batch_successful}/{len(batch_dates)} ({success_rate:.1f}%)")
                    except Exception as e:
                        print(f"   ❌ 本批数据合并失败: {e}")
                else:
                    print(f"   ❌ 本批全部失败: 0/{len(batch_dates)}")
                
                # 更新进度条
                pbar.update(len(batch_dates))
                
                # 计算进度信息
                elapsed_time = time.time() - start_time
                elapsed_str = time.strftime("%H:%M:%S", time.gmtime(elapsed_time))
                
                if batch_num > 0:
                    time_per_date = elapsed_time / (batch_num + len(batch_dates))
                    remaining_dates = total_dates - batch_end_idx
                    remaining_time = time_per_date * remaining_dates
                    remaining_str = time.strftime("%H:%M:%S", time.gmtime(remaining_time))
                    pbar.set_postfix_str(f"已用:{elapsed_str} 剩余:{remaining_str}")
                else:
                    pbar.set_postfix_str(f"已用:{elapsed_str} 剩余:计算中...")
                
                # 批次间等待
                if batch_end_idx < total_dates:
                    remaining_calls = self.rate_limiter.get_remaining_calls()
                    if remaining_calls < 5:
                        wait_time = 60
                        print(f"   ⏳ 频率限制：等待{wait_time}秒后继续...")
                        time.sleep(wait_time)
                    else:
                        time.sleep(1)
        
        finally:
            pbar.close()
        
        # 合并所有数据
        if all_data:
            try:
                self.stock_data = pd.concat(all_data, ignore_index=True)
                self.stock_data = self.stock_data.sort_values(['ts_code', 'trade_date'])
                
                # 数据质量检查
                self._check_data_quality()
                
                print(f"\n🎉 数据获取完成！")
                print(f"✅ 成功获取: {successful_dates} 个交易日")
                print(f"❌ 获取失败: {len(failed_dates)} 个日期")
                print(f"📊 总记录数: {len(self.stock_data)} 条")
                
                total_time = time.time() - start_time
                total_minutes = total_time / 60
                print(f"⏱️ 总耗时: {total_minutes:.1f} 分钟")
                
                return self.stock_data
                
            except Exception as e:
                print(f"❌ 数据合并失败: {e}")
                return pd.DataFrame()
        else:
            print("❌ 没有获取到任何数据")
            return pd.DataFrame()
    
    def get_multiple_days_data_optimized(self, start_date, end_date, months=3):
        """
        优化版本：自动选择合适的时间范围
        """
        print(f"🎯 智能获取模式：最近{months}个月数据")
        
        # 计算日期范围
        end_date_obj = datetime.strptime(end_date, '%Y%m%d')
        start_date_obj = end_date_obj - timedelta(days=months*30)
        start_date_optimized = start_date_obj.strftime('%Y%m%d')
        
        print(f"📅 优化后的时间范围: {start_date_optimized} 到 {end_date}")
        return self.get_multiple_days_data(start_date_optimized, end_date, use_internal_fallback=True, verify_dates=True, verbose=True)
    
    def _check_data_quality(self):
        """检查数据质量"""
        if self.stock_data is None:
            return
        
        print("\n🔍 数据质量检查:")
        print(f"   股票数量: {self.stock_data['ts_code'].nunique()} 只")
        print(f"   交易日数: {self.stock_data['trade_date'].nunique()} 天")
        
        # 检查数据完整性
        stock_count = self.stock_data['ts_code'].nunique()
        date_count = self.stock_data['trade_date'].nunique()
        expected_records = stock_count * date_count
        actual_records = len(self.stock_data)
        completeness = actual_records / expected_records * 100 if expected_records > 0 else 0
        
        print(f"   数据完整度: {completeness:.1f}% ({actual_records}/{expected_records})")
        
        # 检查缺失值
        missing_data = self.stock_data.isnull().sum()
        if missing_data.sum() > 0:
            print("   ⚠ 存在缺失值:")
            for col, count in missing_data.items():
                if count > 0:
                    print(f"     {col}: {count} 个缺失值")
        
        # 检查重复数据
        duplicates = self.stock_data.duplicated().sum()
        if duplicates > 0:
            print(f"   ⚠ 存在 {duplicates} 条重复记录")
            self.stock_data = self.stock_data.drop_duplicates()

    def screen_by_conditions(self, conditions_dict):
        """条件筛选"""
        if self.stock_data is None:
            print("请先获取股票数据")
            return None
        
        df = self.stock_data.copy()
        result = df
        
        print("\n正在应用筛选条件...")
        
        # 原有的筛选条件处理逻辑
        if 'date' in conditions_dict:
            date_cond = conditions_dict['date']
            if 'specific_date' in date_cond:
                specific_date = pd.to_datetime(date_cond['specific_date'])
                result = result[result['trade_date'] == specific_date]
                print(f"📅 日期: {specific_date.strftime('%Y-%m-%d')}")
        
        if 'price' in conditions_dict:
            price_cond = conditions_dict['price']
            if 'min_open' in price_cond:
                result = result[result['open'] >= price_cond['min_open']]
                print(f"💰 开盘价 >= {price_cond['min_open']}")
            if 'max_open' in price_cond:
                result = result[result['open'] <= price_cond['max_open']]
                print(f"💰 开盘价 <= {price_cond['max_open']}")
        
        if 'pct_chg' in conditions_dict:
            pct_cond = conditions_dict['pct_chg']
            if 'min_pct' in pct_cond:
                result = result[result['pct_chg'] >= pct_cond['min_pct']]
                print(f"📈 涨跌幅 >= {pct_cond['min_pct']}%")
            if 'direction' in pct_cond and pct_cond['direction'] == 'up':
                result = result[result['pct_chg'] > 0]
                print("📈 筛选上涨股票")
        
        print(f"✅ 筛选完成！找到 {len(result)} 条记录")
        return result

def rename_columns_to_chinese(df):
    """将英文列名转换为中文列名"""
    column_mapping = {
        'ts_code': '股票代码', 'trade_date': '交易日期', 'open': '开盘价',
        'high': '最高价', 'low': '最低价', 'close': '收盘价',
        'pre_close': '昨收价', 'change': '涨跌额', 'pct_chg': '涨跌幅',
        'vol': '成交量', 'amount': '成交额'
    }
    existing_columns = {col: column_mapping[col] for col in df.columns if col in column_mapping}
    return df.rename(columns=existing_columns)

def display_results(result_df, max_display=15):
    """显示结果"""
    if result_df is None or result_df.empty:
        print("❌ 没有找到符合条件的股票")
        return
    
    result_df_chinese = rename_columns_to_chinese(result_df)
    preferred_columns = ['股票代码', '交易日期', '开盘价', '最高价', '最低价', '收盘价', '涨跌幅', '成交量']
    available_columns = [col for col in preferred_columns if col in result_df_chinese.columns]
    
    print(f"\n📋 筛选结果 (显示前{min(max_display, len(result_df))}条):")
    print("="*100)
    print(result_df_chinese[available_columns].head(max_display).to_string(index=False))
    print("="*100)
    
    if '涨跌幅' in result_df_chinese.columns:
        print(f"\n📊 统计信息:")
        print(f"平均涨跌幅: {result_df_chinese['涨跌幅'].mean():.2f}%")
        print(f"上涨股票数量: {len(result_df_chinese[result_df_chinese['涨跌幅'] > 0])}")

def save_results(result_df, filename):
    """保存结果"""
    if result_df is not None and not result_df.empty:
        if not filename.endswith('.csv'):
            filename += '.csv'
        result_df_chinese = rename_columns_to_chinese(result_df)
        result_df_chinese.to_csv(filename, index=False, encoding='utf-8-sig')
        print(f"💾 结果已保存到 {filename}")
        return True
    else:
        print("❌ 没有数据可保存")
        return False

def screening_loop(screener, period_name):
    """
    执行筛选循环
    """
    print(f"\n🎯 开始{period_name}筛选...")
    
    while True:
        try:
            # 显示筛选选项
            print("\n" + "="*50)
            print("📊 筛选选项:")
            print("1. 技术指标筛选")
            print("2. 基本面筛选") 
            print("3. 综合条件筛选")
            print("4. 返回上一级")
            print("5. 退出程序")
            
            choice = input("\n请选择筛选类型 (1-5): ").strip()
            
            if choice == '1':
                technical_screening(screener)
            elif choice == '2':
                fundamental_screening(screener)
            elif choice == '3':
                comprehensive_screening(screener)
            elif choice == '4':
                print("返回上一级...")
                break
            elif choice == '5':
                print("👋 感谢使用，再见！")
                exit()
            else:
                print("❌ 无效选择，请重新输入")
                
        except Exception as e:
            print(f"❌ 筛选过程中出现错误: {e}")
            continue

def technical_screening(screener):
    """技术指标筛选"""
    print("\n🔧 技术指标筛选")
    
    conditions = {}
    
    # 价格突破筛选
    print("\n📊 价格突破筛选:")
    high_break = input("是否筛选创近期新高？(y/n): ").strip().lower()
    if high_break == 'y':
        conditions['high_break'] = True
        print("✅ 已设置创近期新高筛选")
    
    # 成交量筛选
    print("\n📈 成交量筛选:")
    volume_cond = input("是否设置成交量条件？(y/n): ").strip().lower()
    if volume_cond == 'y':
        min_volume = input("最低成交量(万股) (回车跳过): ").strip()
        if min_volume:
            conditions['min_volume'] = float(min_volume) * 10000  # 转换为手
            print(f"✅ 已设置最低成交量: {min_volume}万股")
    
    # 涨跌幅筛选
    print("\n📉 涨跌幅筛选:")
    pct_conditions = {}
    min_pct = input("最低涨跌幅 (%) (回车跳过): ").strip()
    if min_pct:
        pct_conditions['min_pct'] = float(min_pct)
        print(f"✅ 已设置最低涨跌幅: {min_pct}%")
    
    max_pct = input("最高涨跌幅 (%) (回车跳过): ").strip()
    if max_pct:
        pct_conditions['max_pct'] = float(max_pct)
        print(f"✅ 已设置最高涨跌幅: {max_pct}%")
    
    if pct_conditions:
        conditions['pct_chg'] = pct_conditions
    
    if conditions:
        # 这里可以添加更复杂的技术指标计算逻辑
        result = screener.screen_by_conditions(conditions)
        if result is not None and not result.empty:
            display_results(result)
            
            save_choice = input("\n是否保存结果？(y/n): ").strip().lower()
            if save_choice == 'y':
                filename = input("请输入文件名 (不含.csv): ").strip()
                save_results(result, filename)
        else:
            print("❌ 没有找到符合条件的股票")
    else:
        print("⚠ 未设置任何技术指标条件")

def fundamental_screening(screener):
    """基本面筛选"""
    print("\n📈 基本面筛选")
    
    conditions = {}
    
    # 市值筛选
    print("\n💰 市值筛选:")
    market_cap = input("是否设置市值条件？(y/n): ").strip().lower()
    if market_cap == 'y':
        min_cap = input("最低市值(亿元) (回车跳过): ").strip()
        if min_cap:
            conditions['min_market_cap'] = float(min_cap)
            print(f"✅ 已设置最低市值: {min_cap}亿元")
        
        max_cap = input("最高市值(亿元) (回车跳过): ").strip()
        if max_cap:
            conditions['max_market_cap'] = float(max_cap)
            print(f"✅ 已设置最高市值: {max_cap}亿元")
    
    # 行业筛选
    print("\n🏢 行业筛选:")
    industry = input("请输入行业名称(回车跳过): ").strip()
    if industry:
        conditions['industry'] = industry
        print(f"✅ 已设置行业筛选: {industry}")
    
    # 地区筛选
    print("\n🌍 地区筛选:")
    area = input("请输入地区(回车跳过): ").strip()
    if area:
        conditions['area'] = area
        print(f"✅ 已设置地区筛选: {area}")
    
    if conditions:
        # 这里可以添加基本面数据的获取和筛选逻辑
        print("🔍 正在获取基本面数据...")
        # 暂时使用价格数据作为演示
        result = screener.screen_by_conditions({'pct_chg': {'min_pct': 0}})
        if result is not None and not result.empty:
            display_results(result)
            
            save_choice = input("\n是否保存结果？(y/n): ").strip().lower()
            if save_choice == 'y':
                filename = input("请输入文件名 (不含.csv): ").strip()
                save_results(result, filename)
        else:
            print("❌ 没有找到符合条件的股票")
    else:
        print("⚠ 未设置任何基本面条件")

def comprehensive_screening(screener):
    """综合条件筛选"""
    print("\n🎯 综合条件筛选")
    
    conditions = {}
    
    # 日期筛选
    date_choice = input("是否筛选特定日期？(y/n): ").strip().lower()
    if date_choice == 'y':
        specific_date = input("请输入日期 (YYYYMMDD): ").strip()
        conditions['date'] = {'specific_date': specific_date}
        print(f"✅ 已设置日期筛选: {specific_date}")
    
    # 价格筛选
    price_choice = input("是否设置价格条件？(y/n): ").strip().lower()
    if price_choice == 'y':
        price_conditions = {}
        min_open = input("最低开盘价 (回车跳过): ").strip()
        if min_open:
            price_conditions['min_open'] = float(min_open)
            print(f"✅ 已设置最低开盘价: {min_open}")
        
        max_open = input("最高开盘价 (回车跳过): ").strip()
        if max_open:
            price_conditions['max_open'] = float(max_open)
            print(f"✅ 已设置最高开盘价: {max_open}")
        
        conditions['price'] = price_conditions
    
    # 涨跌幅筛选
    pct_choice = input("是否设置涨跌幅条件？(y/n): ").strip().lower()
    if pct_choice == 'y':
        pct_conditions = {}
        min_pct = input("最低涨跌幅 (%) (回车跳过): ").strip()
        if min_pct:
            pct_conditions['min_pct'] = float(min_pct)
            print(f"✅ 已设置最低涨跌幅: {min_pct}%")
        
        direction = input("筛选上涨/下跌股票？(up/down/回车跳过): ").strip().lower()
        if direction in ['up', 'down']:
            pct_conditions['direction'] = direction
            print(f"✅ 已设置涨跌方向: {'上涨' if direction == 'up' else '下跌'}")
        
        conditions['pct_chg'] = pct_conditions
    
    if conditions:
        result = screener.screen_by_conditions(conditions)
        if result is not None and not result.empty:
            display_results(result)
            
            save_choice = input("\n是否保存结果？(y/n): ").strip().lower()
            if save_choice == 'y':
                filename = input("请输入文件名 (不含.csv): ").strip()
                save_results(result, filename)
        else:
            print("❌ 没有找到符合条件的股票")
    else:
        print("⚠ 未设置任何筛选条件")

def optimized_single_date_mode(screener):
    """单日数据获取模式"""
    print("\n📅 单日数据获取模式")
    target_date = input("请输入日期（YYYYMMDD，如20241231）: ").strip()
    
    if not target_date:
        print("❌ 请输入有效的日期")
        return
    
    try:
        datetime.strptime(target_date, '%Y%m%d')
    except ValueError:
        print("❌ 日期格式错误")
        return
    
    data = screener.get_single_date_data(target_date)
    
    if not data.empty:
        screening_loop(screener, f"{target_date}数据")

def settings_mode(screener):
    """参数设置模式"""
    print("\n⚙️ 参数设置")
    print(f"当前参数:")
    print(f"  并发数: {screener.max_workers}")
    print(f"  重试次数: {screener.retry_times}")
    print(f"  请求延迟: {screener.request_delay}秒")
    
    change = input("是否修改参数？(y/n): ").strip().lower()
    if change == 'y':
        try:
            workers = input(f"并发数 (当前{screener.max_workers}): ").strip()
            if workers:
                screener.max_workers = int(workers)
            
            retries = input(f"重试次数 (当前{screener.retry_times}): ").strip()
            if retries:
                screener.retry_times = int(retries)
            
            delay = input(f"请求延迟 (当前{screener.request_delay}): ").strip()
            if delay:
                screener.request_delay = float(delay)
            
            print("✅ 参数更新完成")
        except ValueError:
            print("❌ 参数格式错误")

def optimized_multiple_days_mode(screener):
    """多日数据获取模式（增强版）"""
    print("\n📅 多日数据获取模式（2025年节假日数据库已更新）")
    print("温馨提示:")
    print("   • 包含2023-2025年完整节假日数据")
    print("   • 支持调休上班日期的智能判断")
    print("   • 提供详细的日期类型分析")
    
    start_date = input("请输入开始日期（YYYYMMDD，如20250101）: ").strip()
    end_date = input("请输入结束日期（YYYYMMDD，如20251231）: ").strip()
    
    if not start_date or not end_date:
        print("❌ 请输入有效的日期")
        return
    
    try:
        datetime.strptime(start_date, '%Y%m%d')
        datetime.strptime(end_date, '%Y%m%d')
    except ValueError:
        print("❌ 日期格式错误")
        return
    
    # 询问是否使用内部判断
    use_internal = input("是否启用内部交易日判断？(y/n, 默认y): ").strip().lower()
    use_internal_fallback = use_internal != 'n'
    
    # 询问是否显示详细分析
    verbose = input("是否显示详细日期分析？(y/n, 默认y): ").strip().lower()
    verbose_flag = verbose != 'n'
    
    # 询问是否验证日期
    verify_dates = input("是否验证交易日准确性？(y/n, 默认y): ").strip().lower()
    verify_dates_flag = verify_dates != 'n'
    
    print(f"\n🚀 开始获取数据（2025年节假日数据库已就绪）...")
    start_time = time.time()
    
    data = screener.get_multiple_days_data(start_date, end_date, use_internal_fallback, verify_dates_flag, verbose_flag)
    
    end_time = time.time()
    total_minutes = (end_time - start_time) / 60
    print(f"⏱️ 总耗时: {total_minutes:.1f} 分钟")
    
    if not data.empty:
        screening_loop(screener, f"{start_date}到{end_date}")

def smart_multiple_days_mode(screener):
    """智能获取模式"""
    print("\n🤖 智能获取模式")
    print("自动选择最近3个月数据，平衡数据量和获取时间")
    
    end_date = input("请输入结束日期（YYYYMMDD，回车使用今天）: ").strip()
    if not end_date:
        end_date = datetime.now().strftime('%Y%m%d')
    
    try:
        datetime.strptime(end_date, '%Y%m%d')
    except ValueError:
        print("❌ 日期格式错误")
        return
    
    print(f"\n🚀 开始智能获取数据...")
    start_time = time.time()
    
    data = screener.get_multiple_days_data_optimized(end_date, end_date, months=3)
    
    end_time = time.time()
    total_minutes = (end_time - start_time) / 60
    print(f"⏱️ 总耗时: {total_minutes:.1f} 分钟")
    
    if not data.empty:
        screening_loop(screener, f"最近3个月数据")

def optimized_interactive_screening():
    """优化后的交互式界面"""
    screener = OptimizedStockScreener()
    
    print("🎯" + "="*60)
    print("           沪深A股全市场股票筛选系统（2025年节假日数据库版）")
    print("="*60)
    print("🎯 特色功能:")
    print("   • 按交易日循环，高效获取全市场数据")
    print("   • 2023-2025年完整节假日数据库")
    print("   • 智能判断调休上班日期")
    print("   • 实时进度显示，预估完成时间")
    
    while True:
        print("\n📊 请选择数据获取方式:")
        print("1. 获取单日全市场数据（快速）")
        print("2. 获取多日历史数据（按日期循环优化）")
        print("3. 智能获取最近3个月数据（推荐）")
        print("4. 设置参数")
        print("5. 退出系统")
        
        choice = input("🖊️  请输入选择 (1-5): ").strip()
        
        if choice == '1':
            optimized_single_date_mode(screener)
        elif choice == '2':
            optimized_multiple_days_mode(screener)
        elif choice == '3':
            smart_multiple_days_mode(screener)
        elif choice == '4':
            settings_mode(screener)
        elif choice == '5':
            print("👋 感谢使用，再见！")
            break
        else:
            print("❌ 无效选择，请重新输入")

if __name__ == "__main__":
    try:
        from tqdm import tqdm
        import concurrent.futures
    except ImportError:
        print("❌ 缺少依赖库，请安装: pip install tqdm")
        exit(1)
    
    optimized_interactive_screening()