#import <Cocoa/Cocoa.h>
#import <arpa/inet.h>
#import <ifaddrs.h>
#import <net/if.h>
#import <unistd.h>

static NSString *const AMServiceName = @"com.airmac.remote";
static NSString *const AMHealthURL = @"http://127.0.0.1:8000/api/health";

@interface AMMenuBarController : NSObject <NSApplicationDelegate, NSMenuDelegate>
@property(nonatomic, strong) NSStatusItem *statusItem;
@property(nonatomic, strong) NSMenu *menu;
@property(nonatomic, copy) NSString *projectDirectory;
@property(nonatomic, copy) NSString *pythonExecutable;
@property(nonatomic, copy) NSString *deviceStorePath;
@property(nonatomic, copy) NSString *logPath;
@property(nonatomic, copy) NSString *healthStatus;
@property(nonatomic, copy) NSString *controllerStatus;
@property(nonatomic, strong) NSArray<NSDictionary *> *devices;
@property(nonatomic, strong) NSTimer *refreshTimer;
@end

@implementation AMMenuBarController

- (instancetype)init {
    self = [super init];
    if (!self) return nil;

    NSArray<NSString *> *arguments = NSProcessInfo.processInfo.arguments;
    NSString *executableDirectory = arguments.firstObject.stringByDeletingLastPathComponent;
    NSString *home = NSHomeDirectory();
    _projectDirectory = arguments.count > 1 ? arguments[1] : executableDirectory;
    _pythonExecutable = arguments.count > 2 ? arguments[2] : @"/usr/bin/python3";
    _deviceStorePath = arguments.count > 3
        ? arguments[3]
        : [home stringByAppendingPathComponent:@"Library/Application Support/AirMac/authorized_devices.json"];
    _logPath = arguments.count > 4
        ? arguments[4]
        : [home stringByAppendingPathComponent:@"Library/Logs/AirMac/remote.log"];
    _healthStatus = @"unknown";
    _controllerStatus = @"idle";
    _devices = @[];
    return self;
}

- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    [NSApp setActivationPolicy:NSApplicationActivationPolicyAccessory];
    self.statusItem = [NSStatusBar.systemStatusBar statusItemWithLength:NSSquareStatusItemLength];
    self.menu = [[NSMenu alloc] initWithTitle:@"AirMac"];
    self.menu.delegate = self;
    self.statusItem.menu = self.menu;
    [self configureStatusButton];
    [self loadDevices];
    [self rebuildMenu];
    [self refreshHealth];
    self.refreshTimer = [NSTimer scheduledTimerWithTimeInterval:5
                                                         target:self
                                                       selector:@selector(refreshHealth)
                                                       userInfo:nil
                                                        repeats:YES];
}

- (void)applicationWillTerminate:(NSNotification *)notification {
    [self.refreshTimer invalidate];
}

- (void)menuNeedsUpdate:(NSMenu *)menu {
    [self loadDevices];
    [self rebuildMenu];
    [self refreshHealth];
}

- (void)configureStatusButton {
    NSStatusBarButton *button = self.statusItem.button;
    if (!button) return;
    if (@available(macOS 11.0, *)) {
        NSImage *image = [NSImage imageWithSystemSymbolName:@"cursorarrow.motionlines"
                                accessibilityDescription:@"AirMac"];
        if (image) {
            button.image = image;
            button.image.template = YES;
        } else {
            button.title = @"A";
        }
    } else {
        button.title = @"A";
    }
    button.toolTip = @"AirMac";
}

- (void)refreshHealth {
    NSMutableURLRequest *request = [NSMutableURLRequest requestWithURL:[NSURL URLWithString:AMHealthURL]];
    request.timeoutInterval = 2;
    __weak typeof(self) weakSelf = self;
    NSURLSessionDataTask *task = [NSURLSession.sharedSession
        dataTaskWithRequest:request
          completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
              NSDictionary *payload = nil;
              if (data) {
                  payload = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
              }
              NSString *status = [payload[@"status"] isKindOfClass:NSString.class]
                  ? payload[@"status"] : @"offline";
              NSString *controller = [payload[@"controller"] isKindOfClass:NSString.class]
                  ? payload[@"controller"] : @"idle";
              dispatch_async(dispatch_get_main_queue(), ^{
                  typeof(self) strongSelf = weakSelf;
                  if (!strongSelf) return;
                  strongSelf.healthStatus = status;
                  strongSelf.controllerStatus = controller;
                  strongSelf.statusItem.button.contentTintColor = [status isEqualToString:@"ok"]
                      ? nil : NSColor.systemRedColor;
                  strongSelf.statusItem.button.toolTip = [status isEqualToString:@"ok"]
                      ? @"AirMac 正在运行" : @"AirMac 后台服务未连接";
              });
          }];
    [task resume];
}

- (void)loadDevices {
    NSData *data = [NSData dataWithContentsOfFile:self.deviceStorePath];
    NSDictionary *database = data
        ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil]
        : nil;
    NSDictionary *records = [database[@"devices"] isKindOfClass:NSDictionary.class]
        ? database[@"devices"] : @{};
    NSMutableArray<NSDictionary *> *devices = [NSMutableArray array];
    [records enumerateKeysAndObjectsUsingBlock:^(NSString *deviceID, NSDictionary *record, BOOL *stop) {
        if (![deviceID isKindOfClass:NSString.class] || ![record isKindOfClass:NSDictionary.class]) return;
        NSMutableDictionary *device = [record mutableCopy];
        device[@"device_id"] = deviceID;
        [devices addObject:device];
    }];
    [devices sortUsingComparator:^NSComparisonResult(NSDictionary *left, NSDictionary *right) {
        NSString *leftDate = left[@"last_seen"] ?: left[@"created_at"] ?: @"";
        NSString *rightDate = right[@"last_seen"] ?: right[@"created_at"] ?: @"";
        return [rightDate compare:leftDate];
    }];
    self.devices = devices;
}

- (void)rebuildMenu {
    [self.menu removeAllItems];
    NSString *statusText;
    if (![self.healthStatus isEqualToString:@"ok"]) {
        statusText = @"后台服务未连接";
    } else if ([self.controllerStatus isEqualToString:@"connected"]) {
        statusText = @"服务运行中 · 手机正在控制";
    } else {
        statusText = @"服务运行中 · 等待手机连接";
    }
    NSMenuItem *status = [[NSMenuItem alloc] initWithTitle:statusText action:nil keyEquivalent:@""];
    status.enabled = NO;
    [self.menu addItem:status];
    [self.menu addItem:NSMenuItem.separatorItem];
    [self.menu addItem:[self itemWithTitle:@"在此 Mac 打开控制页面" action:@selector(openController)]];
    [self.menu addItem:[self itemWithTitle:@"拷贝 iPhone 访问地址" action:@selector(copyControllerAddress)]];
    [self.menu addItem:NSMenuItem.separatorItem];

    NSString *headerTitle = [NSString stringWithFormat:@"已配对设备（%lu）", self.devices.count];
    NSMenuItem *header = [[NSMenuItem alloc] initWithTitle:headerTitle action:nil keyEquivalent:@""];
    header.enabled = NO;
    [self.menu addItem:header];
    if (self.devices.count == 0) {
        NSMenuItem *empty = [[NSMenuItem alloc] initWithTitle:@"  暂无设备" action:nil keyEquivalent:@""];
        empty.enabled = NO;
        [self.menu addItem:empty];
    } else {
        for (NSDictionary *device in self.devices) {
            NSString *name = [device[@"name"] isKindOfClass:NSString.class] ? device[@"name"] : @"未知设备";
            NSMenu *deviceMenu = [[NSMenu alloc] initWithTitle:name];
            NSString *seenTitle = [NSString stringWithFormat:@"最近连接：%@", [self formatDate:device[@"last_seen"]]];
            NSMenuItem *lastSeen = [[NSMenuItem alloc] initWithTitle:seenTitle action:nil keyEquivalent:@""];
            lastSeen.enabled = NO;
            [deviceMenu addItem:lastSeen];
            [deviceMenu addItem:NSMenuItem.separatorItem];
            NSMenuItem *revoke = [self itemWithTitle:@"撤销此设备…" action:@selector(revokeDevice:)];
            revoke.representedObject = device[@"device_id"];
            [deviceMenu addItem:revoke];
            NSMenuItem *parent = [[NSMenuItem alloc] initWithTitle:[@"  " stringByAppendingString:name]
                                                            action:nil
                                                     keyEquivalent:@""];
            parent.submenu = deviceMenu;
            [self.menu addItem:parent];
        }
        [self.menu addItem:[self itemWithTitle:@"撤销全部设备…" action:@selector(clearDevices)]];
    }

    [self.menu addItem:NSMenuItem.separatorItem];
    [self.menu addItem:[self itemWithTitle:@"打开 AirMac 日志" action:@selector(openLogs)]];
    [self.menu addItem:[self itemWithTitle:@"重新启动后台服务" action:@selector(restartService)]];
    [self.menu addItem:NSMenuItem.separatorItem];
    [self.menu addItem:[self itemWithTitle:@"关于 AirMac" action:@selector(showAbout)]];
    [self.menu addItem:[self itemWithTitle:@"退出菜单栏图标" action:@selector(quitMenuBar)]];
}

- (NSMenuItem *)itemWithTitle:(NSString *)title action:(SEL)action {
    NSMenuItem *item = [[NSMenuItem alloc] initWithTitle:title action:action keyEquivalent:@""];
    item.target = self;
    return item;
}

- (NSString *)formatDate:(id)value {
    if (![value isKindOfClass:NSString.class] || [value length] == 0) return @"从未";
    NSISO8601DateFormatter *parser = [[NSISO8601DateFormatter alloc] init];
    parser.formatOptions = NSISO8601DateFormatWithInternetDateTime | NSISO8601DateFormatWithFractionalSeconds;
    NSDate *date = [parser dateFromString:value];
    if (!date) {
        parser.formatOptions = NSISO8601DateFormatWithInternetDateTime;
        date = [parser dateFromString:value];
    }
    if (!date) return value;
    NSDateFormatter *formatter = [[NSDateFormatter alloc] init];
    formatter.dateStyle = NSDateFormatterMediumStyle;
    formatter.timeStyle = NSDateFormatterShortStyle;
    return [formatter stringFromDate:date];
}

- (void)openController {
    [NSWorkspace.sharedWorkspace openURL:[NSURL URLWithString:@"http://127.0.0.1:8000/"]];
}

- (void)copyControllerAddress {
    NSString *address = [NSString stringWithFormat:@"http://%@:8000", [self preferredLANAddress]];
    [NSPasteboard.generalPasteboard clearContents];
    [NSPasteboard.generalPasteboard setString:address forType:NSPasteboardTypeString];
}

- (void)openLogs {
    if ([NSFileManager.defaultManager fileExistsAtPath:self.logPath]) {
        [NSWorkspace.sharedWorkspace activateFileViewerSelectingURLs:@[
            [NSURL fileURLWithPath:self.logPath]
        ]];
    } else {
        [NSWorkspace.sharedWorkspace openURL:[NSURL fileURLWithPath:self.logPath.stringByDeletingLastPathComponent]];
    }
}

- (void)revokeDevice:(NSMenuItem *)sender {
    NSString *deviceID = [sender.representedObject isKindOfClass:NSString.class]
        ? sender.representedObject : nil;
    NSDictionary *device = nil;
    for (NSDictionary *candidate in self.devices) {
        if ([candidate[@"device_id"] isEqualToString:deviceID]) {
            device = candidate;
            break;
        }
    }
    if (!deviceID || !device) return;
    NSString *name = [device[@"name"] isKindOfClass:NSString.class] ? device[@"name"] : @"此设备";
    NSAlert *alert = [[NSAlert alloc] init];
    alert.messageText = [NSString stringWithFormat:@"撤销 %@？", name];
    alert.informativeText = @"这台设备会在约一秒内断开，下次使用时需要重新配对。";
    alert.alertStyle = NSAlertStyleWarning;
    [alert addButtonWithTitle:@"撤销"];
    [alert addButtonWithTitle:@"取消"];
    if ([alert runModal] == NSAlertFirstButtonReturn) {
        [self runDeviceCommand:@[@"revoke", deviceID]];
    }
}

- (void)clearDevices {
    NSAlert *alert = [[NSAlert alloc] init];
    alert.messageText = @"撤销全部已配对设备？";
    alert.informativeText = @"所有手机都需要重新进行六位验证码配对。";
    alert.alertStyle = NSAlertStyleCritical;
    [alert addButtonWithTitle:@"全部撤销"];
    [alert addButtonWithTitle:@"取消"];
    if ([alert runModal] == NSAlertFirstButtonReturn) {
        [self runDeviceCommand:@[@"clear", @"--yes"]];
    }
}

- (void)runDeviceCommand:(NSArray<NSString *> *)arguments {
    NSTask *task = [[NSTask alloc] init];
    task.executableURL = [NSURL fileURLWithPath:self.pythonExecutable];
    task.arguments = [@[[self.projectDirectory stringByAppendingPathComponent:@"manage_devices.py"]]
        arrayByAddingObjectsFromArray:arguments];
    task.currentDirectoryURL = [NSURL fileURLWithPath:self.projectDirectory];
    task.standardOutput = [NSPipe pipe];
    task.standardError = [NSPipe pipe];
    __weak typeof(self) weakSelf = self;
    task.terminationHandler = ^(NSTask *completed) {
        dispatch_async(dispatch_get_main_queue(), ^{
            typeof(self) strongSelf = weakSelf;
            if (!strongSelf) return;
            [strongSelf loadDevices];
            [strongSelf rebuildMenu];
            if (completed.terminationStatus != 0) {
                [strongSelf showMessage:@"设备管理失败"
                                 detail:@"命令未成功执行，请查看 AirMac 日志或重新安装服务。"
                                  style:NSAlertStyleWarning];
            }
        });
    };
    NSError *error = nil;
    if (![task launchAndReturnError:&error]) {
        [self showMessage:@"无法运行设备管理" detail:error.localizedDescription style:NSAlertStyleWarning];
    }
}

- (void)restartService {
    NSTask *task = [[NSTask alloc] init];
    task.executableURL = [NSURL fileURLWithPath:@"/bin/launchctl"];
    task.arguments = @[@"kickstart", @"-k", [NSString stringWithFormat:@"gui/%d/%@", getuid(), AMServiceName]];
    task.standardOutput = [NSPipe pipe];
    task.standardError = [NSPipe pipe];
    __weak typeof(self) weakSelf = self;
    task.terminationHandler = ^(NSTask *completed) {
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
            typeof(self) strongSelf = weakSelf;
            [strongSelf refreshHealth];
            if (completed.terminationStatus != 0) {
                [strongSelf showMessage:@"后台服务重启失败"
                                 detail:@"请运行 install_service.sh 重新安装。"
                                  style:NSAlertStyleWarning];
            }
        });
    };
    NSError *error = nil;
    if (![task launchAndReturnError:&error]) {
        [self showMessage:@"无法重启后台服务" detail:error.localizedDescription style:NSAlertStyleWarning];
    }
}

- (void)showAbout {
    [self showMessage:@"AirMac"
               detail:@"可信局域网中的 iPhone 触控板与键盘。\n菜单栏退出不会停止后台服务。"
                style:NSAlertStyleInformational];
}

- (void)quitMenuBar {
    [NSApp terminate:nil];
}

- (void)showMessage:(NSString *)title detail:(NSString *)detail style:(NSAlertStyle)style {
    NSAlert *alert = [[NSAlert alloc] init];
    alert.messageText = title;
    alert.informativeText = detail;
    alert.alertStyle = style;
    [alert addButtonWithTitle:@"好"];
    [alert runModal];
}

- (NSString *)preferredLANAddress {
    struct ifaddrs *interfaces = NULL;
    if (getifaddrs(&interfaces) != 0) return @"127.0.0.1";
    NSString *result = nil;
    for (struct ifaddrs *current = interfaces; current; current = current->ifa_next) {
        if (!current->ifa_addr || current->ifa_addr->sa_family != AF_INET) continue;
        if (!(current->ifa_flags & IFF_UP) || (current->ifa_flags & IFF_LOOPBACK)) continue;
        char buffer[INET_ADDRSTRLEN] = {0};
        struct sockaddr_in *address = (struct sockaddr_in *)current->ifa_addr;
        if (!inet_ntop(AF_INET, &address->sin_addr, buffer, sizeof(buffer))) continue;
        NSString *candidate = [NSString stringWithUTF8String:buffer];
        NSArray<NSString *> *parts = [candidate componentsSeparatedByString:@"."];
        if (parts.count != 4) continue;
        NSInteger first = parts[0].integerValue;
        NSInteger second = parts[1].integerValue;
        BOOL privateAddress = first == 10
            || (first == 172 && second >= 16 && second <= 31)
            || (first == 192 && second == 168);
        if (privateAddress) {
            result = candidate;
            break;
        }
    }
    freeifaddrs(interfaces);
    return result ?: @"127.0.0.1";
}

@end

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        NSApplication *application = NSApplication.sharedApplication;
        AMMenuBarController *controller = [[AMMenuBarController alloc] init];
        application.delegate = controller;
        [application run];
    }
    return 0;
}
