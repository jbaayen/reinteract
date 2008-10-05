/* -*- mode: ObjC; c-basic-offset: 4; indent-tabs-mode: nil; -*-
 *
 * Copyright 2008 Owen Taylor
 *
 * This file is part of Reinteract and distributed under the terms
 * of the BSD license. See the file COPYING in the Reinteract
 * distribution for full details.
 *
 ************************************************************************/

#import <Cocoa/Cocoa.h>

typedef void (*MenuActionCallback) (NSString *actionName, void *data);

// Delegate for menu items. See MenuController.m for a description
@interface MenuController : NSObject {
    // Mapping from action name to the menu item object
    NSMutableDictionary *actionToMenuItem;
    // Callback when a menu item is activated
    MenuActionCallback actionCallback;
    void *actionCallbackData;
}

// Sets the callback when menu items are activated
-(void)setActionCallback:(MenuActionCallback) callback callbackData:(void *)callbackData;

// Initializes the action name to menu item mapping with the menu items
// in the menu and in submenus
-(void)addActionsFromMenu:(NSMenu *)menu;

// Enable/disable actions by menu item name
-(void)enableAction:(NSString *)actionName;
-(void)disableAction:(NSString *)actionName;

-(NSArray *)actionNames;

@end
