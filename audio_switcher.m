#import <CoreAudio/CoreAudio.h>
#import <Foundation/Foundation.h>

static BOOL ReadUInt32(AudioObjectID objectID,
                       AudioObjectPropertySelector selector,
                       AudioObjectPropertyScope scope,
                       UInt32 *value) {
    AudioObjectPropertyAddress address = {selector, scope,
                                          kAudioObjectPropertyElementMain};
    UInt32 size = sizeof(*value);
    return AudioObjectGetPropertyData(objectID, &address, 0, NULL, &size,
                                      value) == noErr;
}

static NSString *DeviceName(AudioDeviceID deviceID) {
    AudioObjectPropertyAddress address = {kAudioObjectPropertyName,
                                          kAudioObjectPropertyScopeGlobal,
                                          kAudioObjectPropertyElementMain};
    CFStringRef value = NULL;
    UInt32 size = sizeof(value);
    if (AudioObjectGetPropertyData(deviceID, &address, 0, NULL, &size,
                                   &value) != noErr || value == NULL) {
        return nil;
    }
    return CFBridgingRelease(value);
}

static BOOL HasOutputChannels(AudioDeviceID deviceID) {
    AudioObjectPropertyAddress address = {
        kAudioDevicePropertyStreamConfiguration,
        kAudioDevicePropertyScopeOutput,
        kAudioObjectPropertyElementMain,
    };
    UInt32 size = 0;
    if (AudioObjectGetPropertyDataSize(deviceID, &address, 0, NULL, &size) !=
            noErr ||
        size == 0) {
        return NO;
    }
    AudioBufferList *buffers = malloc(size);
    if (buffers == NULL) {
        return NO;
    }
    BOOL hasChannels = NO;
    if (AudioObjectGetPropertyData(deviceID, &address, 0, NULL, &size,
                                   buffers) == noErr) {
        for (UInt32 index = 0; index < buffers->mNumberBuffers; index++) {
            if (buffers->mBuffers[index].mNumberChannels > 0) {
                hasChannels = YES;
                break;
            }
        }
    }
    free(buffers);
    return hasChannels;
}

static NSArray<NSDictionary *> *OutputDevices(void) {
    AudioObjectPropertyAddress address = {kAudioHardwarePropertyDevices,
                                          kAudioObjectPropertyScopeGlobal,
                                          kAudioObjectPropertyElementMain};
    UInt32 size = 0;
    if (AudioObjectGetPropertyDataSize(kAudioObjectSystemObject, &address, 0,
                                       NULL, &size) != noErr ||
        size == 0) {
        return @[];
    }
    AudioDeviceID *deviceIDs = malloc(size);
    if (deviceIDs == NULL) {
        return @[];
    }
    if (AudioObjectGetPropertyData(kAudioObjectSystemObject, &address, 0, NULL,
                                   &size, deviceIDs) != noErr) {
        free(deviceIDs);
        return @[];
    }

    NSMutableArray<NSDictionary *> *devices = [NSMutableArray array];
    UInt32 count = size / sizeof(AudioDeviceID);
    for (UInt32 index = 0; index < count; index++) {
        AudioDeviceID deviceID = deviceIDs[index];
        UInt32 alive = 1;
        UInt32 hidden = 0;
        ReadUInt32(deviceID, kAudioDevicePropertyDeviceIsAlive,
                   kAudioObjectPropertyScopeGlobal, &alive);
        ReadUInt32(deviceID, kAudioDevicePropertyIsHidden,
                   kAudioObjectPropertyScopeGlobal, &hidden);
        NSString *name = DeviceName(deviceID);
        if (alive && !hidden && name.length > 0 && HasOutputChannels(deviceID)) {
            [devices addObject:@{ @"id" : @(deviceID), @"name" : name }];
        }
    }
    free(deviceIDs);
    return [devices sortedArrayUsingComparator:^NSComparisonResult(
                        NSDictionary *left, NSDictionary *right) {
        return [left[@"name"] localizedStandardCompare:right[@"name"]];
    }];
}

static BOOL SetSystemDevice(AudioObjectPropertySelector selector,
                            AudioDeviceID deviceID) {
    AudioObjectPropertyAddress address = {selector,
                                          kAudioObjectPropertyScopeGlobal,
                                          kAudioObjectPropertyElementMain};
    UInt32 size = sizeof(deviceID);
    return AudioObjectSetPropertyData(kAudioObjectSystemObject, &address, 0,
                                      NULL, size, &deviceID) == noErr;
}

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc != 2 ||
            (strcmp(argv[1], "cycle") != 0 && strcmp(argv[1], "list") != 0)) {
            fputs("用法：audio-switcher list|cycle\n", stderr);
            return 2;
        }
        UInt32 current = kAudioObjectUnknown;
        if (!ReadUInt32(kAudioObjectSystemObject,
                        kAudioHardwarePropertyDefaultOutputDevice,
                        kAudioObjectPropertyScopeGlobal, &current)) {
            fputs("无法读取当前音频输出设备\n", stderr);
            return 1;
        }
        NSArray<NSDictionary *> *devices = OutputDevices();
        if (devices.count == 0) {
            fputs("没有找到可切换的音频输出设备\n", stderr);
            return 1;
        }
        if (strcmp(argv[1], "list") == 0) {
            for (NSDictionary *device in devices) {
                const char *marker =
                    [device[@"id"] unsignedIntValue] == current ? "*" : " ";
                printf("%s %s\n", marker, [device[@"name"] UTF8String]);
            }
            return 0;
        }

        NSUInteger currentIndex = [devices indexOfObjectPassingTest:^BOOL(
            NSDictionary *device, NSUInteger index, BOOL *stop) {
            (void)index;
            (void)stop;
            return [device[@"id"] unsignedIntValue] == current;
        }];
        NSUInteger nextIndex = currentIndex == NSNotFound
                                   ? 0
                                   : (currentIndex + 1) % devices.count;
        NSDictionary *next = devices[nextIndex];
        AudioDeviceID nextID = [next[@"id"] unsignedIntValue];
        if (!SetSystemDevice(kAudioHardwarePropertyDefaultOutputDevice,
                             nextID)) {
            fputs("无法切换音频输出设备\n", stderr);
            return 1;
        }
        SetSystemDevice(kAudioHardwarePropertyDefaultSystemOutputDevice, nextID);
        puts([next[@"name"] UTF8String]);
    }
    return 0;
}
